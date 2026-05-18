#!/usr/bin/env python3
"""
bt_timestamp_compare_macos.py

Bluetooth Timestamp Triangulation Tool — macOS Edition
T1 is recorded at the end of a countdown — act immediately after.

Timestamps captured per trial:
  T1 - Ground truth:    end of countdown (system clock, UTC)
  T2 - Unified Log:     timestamp recorded inside the Unified Log entry
  T3 - plist detection: moment script noticed plist file change
  T4 - plist mtime:     filesystem write time of com.apple.Bluetooth.plist
  T4v- plist value:     LastSeenTime value embedded inside the plist

Key columns in CSV:
  delta_T2_minus_T1_ms     — Unified Log write delay
  delta_T3_minus_T1_ms     — plist detection latency
  delta_T4_mtime_minus_T1  — plist filesystem write delay
  delta_T4_value_minus_T1  — embedded LastSeen value accuracy
  skew_T2_minus_T3_ms      — Unified Log vs system clock (should be ~0 on macOS)

Usage:
    python3 bt_timestamp_compare_macos.py

Requirements:
    macOS 13+ (Ventura/Sonoma/Sequoia/Tahoe), Python 3.10+
    No pip dependencies — stdlib + macOS system tools only
    Run as normal user.
"""

import sys
import os
import csv
import time
import subprocess
import threading
import json
import re
from datetime import datetime, timezone, timedelta

# CONFIG

PLIST_PATH       = os.path.expanduser("~/Library/Preferences/com.apple.Bluetooth.plist")
BT_LOG_PREDICATE = 'subsystem == "com.apple.bluetooth"'

PAIR_KEYWORDS   = ["connected", "paired", "link key created",
                   "bonded", "connection complete", "hid device added"]
REMOVE_KEYWORDS = ["removed", "forget", "unpaired", "link key deleted",
                   "device deleted", "removing device"]

CSV_OUTPUT    = "bt_timestamps_macos.csv"
POLL_INTERVAL = 0.05   # 50ms

# Seconds of countdown after Enter before T1 is recorded.
# Use this time to move your mouse over the confirmation button.
# Set to 0 to record T1 immediately on Enter.
PRE_T1_COUNTDOWN_SECONDS = 5

COCOA_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

# HELPERS

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def fmt(dt: datetime) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

def delta_ms(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() * 1000

def cocoa_to_utc(ts: float) -> datetime:
    return COCOA_EPOCH + timedelta(seconds=float(ts))

# COUNTDOWN

def countdown_and_mark(seconds: int) -> datetime:
    """
    Count down visually, then record and return T1.
    Use the countdown to position your mouse over the confirmation button.
    Act immediately when the countdown hits 0.
    """
    if seconds <= 0:
        return now_utc()
    print(f"\n  Move your mouse over the button — acting in {seconds}s...")
    for i in range(seconds, 0, -1):
        print(f"  {i}...", end="\r", flush=True)
        time.sleep(1)
    T1 = now_utc()
    print("  ACT NOW!                        ", flush=True)
    return T1

# PLIST HELPERS

def get_plist_mtime() -> datetime | None:
    try:
        mtime = os.path.getmtime(PLIST_PATH)
        return datetime.fromtimestamp(mtime, tz=timezone.utc)
    except Exception:
        return None

def read_plist_last_seen() -> tuple:
    """
    Read com.apple.Bluetooth.plist and return the most recently updated
    LastSeenTime / LastConnected value across all paired devices.
    Returns (device_name, utc_datetime) or (None, None).
    """
    try:
        r = subprocess.run(
            ["plutil", "-convert", "json", "-o", "-", PLIST_PATH],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            return None, None

        data = json.loads(r.stdout)
        latest_dt   = None
        latest_name = None

        for section_key in ("DeviceCache", "PairedDevices", "KnownDevices"):
            section = data.get(section_key, {})
            if not isinstance(section, dict):
                continue
            for addr, info in section.items():
                if not isinstance(info, dict):
                    continue
                for ts_key in ("LastSeenTime", "LastConnected", "LastConnectedTime"):
                    raw = info.get(ts_key)
                    if raw is not None:
                        try:
                            dt = cocoa_to_utc(raw)
                            if latest_dt is None or dt > latest_dt:
                                latest_dt   = dt
                                latest_name = info.get("Name", addr)
                        except Exception:
                            pass
        return latest_name, latest_dt
    except Exception:
        return None, None

# UNIFIED LOG HELPERS

def parse_log_timestamp(line: str) -> datetime | None:
    try:
        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)[+-]\d{4}", line)
        if m:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")
            return dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None

def classify_log_line(line: str) -> str | None:
    lower = line.lower()
    if any(k in lower for k in PAIR_KEYWORDS):
        return "paired"
    if any(k in lower for k in REMOVE_KEYWORDS):
        return "removed"
    return None

def query_unified_log_once(since: datetime) -> dict | None:
    """Single log show query for Bluetooth events after `since`."""
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    try:
        r = subprocess.run(
            ["log", "show",
             "--predicate", BT_LOG_PREDICATE,
             "--info",
             "--start", since_str,
             "--style", "compact"],
            capture_output=True, text=True, timeout=10
        )
        lines = [l for l in r.stdout.splitlines()
                 if l.strip() and not l.startswith("Filtering")]
        for line in lines:
            ev_type = classify_log_line(line)
            if ev_type is None:
                continue
            T2 = parse_log_timestamp(line)
            if T2 is None or T2 <= since:
                continue
            return {
                "T2_log_time": T2,
                "label":       ("PAIRED   (Unified Log)"
                                if ev_type == "paired"
                                else "REMOVED  (Unified Log)"),
                "description": line.strip()[:120],
            }
    except Exception as e:
        print(f"  [!] Log query error: {e}")
    return None

# ─── PLIST WATCHER ────────────────────────────────────────────────────────────

class PlistWatcher:
    """
    Polls com.apple.Bluetooth.plist mtime every 50ms.
    T3 = moment our script detects a change (system clock).
    T4 = the file's own modification timestamp at that moment.
    """

    def __init__(self):
        self.last_mtime:   datetime | None = get_plist_mtime()
        self.change_time:  datetime | None = None   # T3
        self.change_mtime: datetime | None = None   # T4
        self._trigger = threading.Event()
        self._running = False

    def start(self):
        self._running = True
        threading.Thread(target=self._poll, daemon=True).start()

    def stop(self):
        self._running = False

    def reset(self):
        self.last_mtime   = get_plist_mtime()
        self.change_time  = None
        self.change_mtime = None
        self._trigger.clear()

    def wait_for_change(self, timeout: int = 60) -> bool:
        return self._trigger.wait(timeout=timeout)

    def _poll(self):
        while self._running:
            time.sleep(POLL_INTERVAL)
            if self._trigger.is_set():
                continue
            try:
                mtime = get_plist_mtime()
                if mtime and self.last_mtime and mtime != self.last_mtime:
                    self.change_time  = now_utc()
                    self.change_mtime = mtime
                    self.last_mtime   = mtime
                    self._trigger.set()
            except Exception:
                pass

# CLOCK SKEW

def describe_skew(skew_ms: float) -> str:
    abs_s     = abs(skew_ms) / 1000
    direction = "ahead of" if skew_ms > 0 else "behind"
    if abs(skew_ms) < 500:
        return "clocks aligned — Unified Log using UTC correctly"
    elif 3590_000 <= abs(skew_ms) <= 3610_000:
        return f"Unified Log {direction} system clock by ~1h | UTC+1 misconfiguration?"
    elif 7190_000 <= abs(skew_ms) <= 7210_000:
        return f"Unified Log {direction} system clock by ~2h | UTC+2 misconfiguration?"
    else:
        return f"Unified Log {direction} system clock by {abs_s:.1f}s | check time settings"

# ─── CSV ──────────────────────────────────────────────────────────────────────

CSV_HEADERS = [
    "trial",
    "event_type",
    "T1_ground_truth_UTC",
    "T2_unified_log_UTC",
    "T3_plist_detection_UTC",
    "T4_plist_mtime_UTC",
    "T4_plist_last_seen_UTC",
    "delta_T2_minus_T1_ms",
    "delta_T3_minus_T1_ms",
    "delta_T4_mtime_minus_T1_ms",
    "delta_T4_value_minus_T1_ms",
    "skew_T2_minus_T3_ms",
    "skew_description",
    "log_entry",
    "notes",
]

def write_csv_row(row: dict):
    exists = os.path.exists(CSV_OUTPUT)
    with open(CSV_OUTPUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not exists:
            w.writeheader()
        w.writerow(row)

# MAIN

def main():
    print("=" * 62)
    print("  Bluetooth Timestamp Triangulation — macOS Edition")
    print("  Stockholm University — CYFO Assignment")
    print("=" * 62)

    print()
    if not os.path.exists(PLIST_PATH):
        print(f"  [!] Plist not found: {PLIST_PATH}")
        print("      Make sure Bluetooth is on and a device has been paired.")
    else:
        print(f"  [OK] Plist:   {PLIST_PATH}")

    r = subprocess.run(["which", "log"], capture_output=True, text=True)
    if r.returncode != 0:
        print("  [!] 'log' CLI not found — macOS 10.12+ required.")
        sys.exit(1)
    print(f"  [OK] log CLI: {r.stdout.strip()}")

    r2 = subprocess.run(["which", "plutil"], capture_output=True, text=True)
    if r2.returncode != 0:
        print("  [!] 'plutil' not found — plist reading will be skipped.")
    else:
        print(f"  [OK] plutil:  {r2.stdout.strip()}")

    print(f"  [OK] Output:  {CSV_OUTPUT}")
    print()
    print(f"  NOTE: No reaction time correction — all deltas include your")
    print(f"  action delay. Report as upper-bound estimates of OS latency.")
    print(f"  Countdown: {PRE_T1_COUNTDOWN_SECONDS}s after Enter, then act immediately at 'ACT NOW!'")

    plist_watcher = PlistWatcher()
    plist_watcher.start()
    print(f"\n  [OK] Plist watcher started (50ms polling).")

    print()
    print("── Trial Protocol ──────────────────────────────────────────")
    print()
    print("  FORGET DEVICE trial:")
    print("    1. System Settings → Bluetooth → your device → (i)")
    print("    2. Click 'Forget This Device'")
    print("    3. Stop at confirmation popup — do NOT confirm yet")
    print("    4. Press ENTER in this terminal")
    print(f"    5. Countdown runs ({PRE_T1_COUNTDOWN_SECONDS}s) — on 'ACT NOW' click Forget")
    print()
    print("  PAIRING trial:")
    print("    1. Forget the device fully first")
    print("    2. Put device into pairing mode")
    print("    3. System Settings → Bluetooth → wait for device")
    print("    4. Do NOT click Connect yet")
    print("    5. Press ENTER in this terminal")
    print(f"    6. Countdown runs ({PRE_T1_COUNTDOWN_SECONDS}s) — on 'ACT NOW' click Connect")
    print("─" * 62)

    trial   = 1
    skew_ms = None

    while True:
        print(f"\n  TRIAL {trial}")
        print("  " + "─" * 40)

        if skew_ms is not None:
            print(f"  [i] Skew from last trial: {skew_ms:+.0f} ms ({skew_ms/1000:+.3f}s)")

        notes = input("\n  Notes for this trial [Enter to skip]: ").strip()
        input("\n  >>> Prepare your action, then press ENTER to start countdown <<<")

        plist_watcher.reset()

        T1 = countdown_and_mark(PRE_T1_COUNTDOWN_SECONDS)
        print(f"\n  T1 (ground truth): {fmt(T1)}")
        print("  Watching plist + Unified Log... (timeout: 60s)")

        # Unified Log polling in background
        log_result_holder = [None]
        log_done_event    = threading.Event()

        def log_thread_fn():
            deadline = time.time() + 60
            while time.time() < deadline:
                result = query_unified_log_once(T1)
                if result:
                    log_result_holder[0] = result
                    break
                time.sleep(POLL_INTERVAL)
            log_done_event.set()

        threading.Thread(target=log_thread_fn, daemon=True).start()

        changed  = plist_watcher.wait_for_change(timeout=60)
        T3       = plist_watcher.change_time
        T4_mtime = plist_watcher.change_mtime

        log_done_event.wait(timeout=60)
        log_result = log_result_holder[0]

        plist_device_name, T4_value = read_plist_last_seen()

        if not changed and log_result is None:
            print("\n  [!] No plist change and no log entry detected within 60s.")
            print("      Make sure you acted immediately at 'ACT NOW!'")
            trial += 1
            cont = input("\n  Try another trial? [Y/n]: ").strip().lower()
            if cont == "n":
                break
            continue

        T2 = log_result["T2_log_time"] if log_result else None

        if T2 and T3:
            skew_ms   = delta_ms(T3, T2)
            skew_desc = describe_skew(skew_ms)
        else:
            skew_desc = "could not measure — T2 or T3 missing"

        d_T2_T1  = delta_ms(T1, T2)        if T2       else None
        d_T3_T1  = delta_ms(T1, T3)        if T3       else None
        d_T4m_T1 = delta_ms(T1, T4_mtime)  if T4_mtime else None
        d_T4v_T1 = delta_ms(T1, T4_value)  if T4_value else None

        label = (log_result["label"] if log_result
                 else ("PLIST CHANGE (no log entry)" if changed else "NO EVENT"))

        print(f"\n  Event type: {label}")
        print(f"  T1 (ground truth):          {fmt(T1)}")
        print(f"  T2 (Unified Log):           {fmt(T2)       if T2       else 'not found'}")
        print(f"  T3 (plist detected):        {fmt(T3)       if T3       else 'not detected'}")
        print(f"  T4 (plist mtime):           {fmt(T4_mtime) if T4_mtime else 'n/a'}")
        print(f"  T4v(plist LastSeen value):  {fmt(T4_value) if T4_value else 'n/a'}"
              + (f"  [{plist_device_name}]" if plist_device_name else ""))

        print(f"\n  ── Deltas ──────────────────────────────────────────")
        if d_T2_T1  is not None: print(f"  T2 - T1  Unified Log delay:    {d_T2_T1:>12.2f} ms")
        if d_T3_T1  is not None: print(f"  T3 - T1  plist detection:      {d_T3_T1:>12.2f} ms")
        if d_T4m_T1 is not None: print(f"  T4m- T1  plist mtime delay:    {d_T4m_T1:>12.2f} ms")
        if d_T4v_T1 is not None: print(f"  T4v- T1  LastSeen value delay: {d_T4v_T1:>12.2f} ms")
        if skew_ms  is not None: print(f"  Skew     T2 - T3:             {skew_ms:>+12.2f} ms")

        t2_str  = f"{d_T2_T1:.1f} ms"  if d_T2_T1  is not None else "n/a"
        t3_str  = f"{d_T3_T1:.1f} ms"  if d_T3_T1  is not None else "n/a"
        t4m_str = f"{d_T4m_T1:.1f} ms" if d_T4m_T1 is not None else "n/a"
        t4v_str = f"{d_T4v_T1:.1f} ms" if d_T4v_T1 is not None else "n/a"
        sk_str  = f"{skew_ms/1000:+.3f}s" if skew_ms is not None else "n/a"

        print(f"\n  ┌───────────────────────────────────────────────────┐")
        print(f"  │  FORENSIC FINDING — Trial {trial:<3}                      │")
        print(f"  │  Unified Log delay:  {t2_str:<34}│")
        print(f"  │  Plist detection:    {t3_str:<34}│")
        print(f"  │  Plist mtime delay:  {t4m_str:<34}│")
        print(f"  │  LastSeen accuracy:  {t4v_str:<34}│")
        print(f"  │  Clock skew:         {sk_str:<34}│")
        print(f"  └───────────────────────────────────────────────────┘")

        row = {
            "trial":                      trial,
            "event_type":                 label,
            "T1_ground_truth_UTC":        fmt(T1),
            "T2_unified_log_UTC":         fmt(T2)       if T2       else "",
            "T3_plist_detection_UTC":     fmt(T3)       if T3       else "",
            "T4_plist_mtime_UTC":         fmt(T4_mtime) if T4_mtime else "",
            "T4_plist_last_seen_UTC":     fmt(T4_value) if T4_value else "",
            "delta_T2_minus_T1_ms":       round(d_T2_T1,  2) if d_T2_T1  is not None else "",
            "delta_T3_minus_T1_ms":       round(d_T3_T1,  2) if d_T3_T1  is not None else "",
            "delta_T4_mtime_minus_T1_ms": round(d_T4m_T1, 2) if d_T4m_T1 is not None else "",
            "delta_T4_value_minus_T1_ms": round(d_T4v_T1, 2) if d_T4v_T1 is not None else "",
            "skew_T2_minus_T3_ms":        round(skew_ms,  2) if skew_ms   is not None else "",
            "skew_description":           skew_desc,
            "log_entry":                  log_result["description"] if log_result else "",
            "notes":                      notes,
        }

        write_csv_row(row)
        print(f"\n  Saved → {CSV_OUTPUT}")

        trial += 1
        cont = input("\n  Run another trial? [Y/n]: ").strip().lower()
        if cont == "n":
            break

    plist_watcher.stop()

    print(f"\n{'=' * 62}")
    print(f"  Done. {trial - 1} trial(s) saved to {CSV_OUTPUT}")
    print(f"{'=' * 62}")
    print()
    print("── Column Guide ────────────────────────────────────────────")
    print()
    print("  delta_T2_minus_T1_ms      Unified Log write delay")
    print("  delta_T3_minus_T1_ms      plist file detection latency")
    print("  delta_T4_mtime_minus_T1   plist filesystem write delay")
    print("  delta_T4_value_minus_T1   LastSeen embedded value accuracy")
    print("  skew_T2_minus_T3_ms       Unified Log vs system clock")
    print("                            (should be ~0ms on macOS)")
    print()
    print("  All deltas include your action delay (no RT correction).")
    print("  Report as upper-bound estimates of OS write latency.")
    print("─" * 62)

if __name__ == "__main__":
    main()
