#!/usr/bin/env python3
"""
bt_timestamp_auto_macos.py

Bluetooth Timestamp Triangulation Tool — macOS Automated Edition
Stockholm University — CYFO Assignment

Fully automated — no human action delay, no beep, no reaction time.
Uses blueutil to toggle Bluetooth off/on programmatically.
T1 is recorded at the exact moment the OS call is made.

Event sequence per trial:
  1. Script calls: blueutil --power 0   (Bluetooth OFF)
  2. T1 recorded immediately after the call returns
  3. Script watches plist + Unified Log for the resulting events
  4. T2, T3, T4 recorded when detected
  5. Script restores: blueutil --power 1  (Bluetooth ON)
  6. Inter-trial pause (configurable) before next trial

Timestamps captured per trial:
  T1 - Ground truth:    moment blueutil call was made (system clock, UTC)
  T2 - Unified Log:     timestamp recorded inside the Unified Log entry
  T3 - plist detection: moment script noticed plist file change
  T4 - plist mtime:     filesystem write time of com.apple.Bluetooth.plist
  T4v- plist value:     LastSeenTime value embedded inside the plist

Key columns in CSV:
  delta_T2_minus_T1_ms      Unified Log write latency  (pure OS delay)
  delta_T3_minus_T1_ms      plist detection latency    (pure OS delay)
  delta_T4_mtime_minus_T1   plist filesystem write delay
  delta_T4_value_minus_T1   LastSeen embedded value accuracy
  skew_T2_minus_T3_ms       Unified Log vs system clock (should be ~0)

Usage:
    python3 bt_timestamp_auto_macos.py

Requirements:
    macOS 13+ (Ventura/Sonoma/Sequoia/Tahoe), Python 3.10+
    blueutil:  brew install blueutil
    No other pip dependencies — stdlib + macOS system tools only

Notes:
    - blueutil toggles the entire Bluetooth adapter on/off
    - This generates real BTHUSB-equivalent events in the Unified Log
    - The plist is updated when Bluetooth is toggled
    - Bluetooth is always restored after each trial (even on error)
    - If blueutil is not found the script prints install instructions
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

# Keywords indicating Bluetooth power-off events in Unified Log
POWER_OFF_KEYWORDS = ["power off", "powered off", "turning off",
                      "bluetooth off", "disabled", "power state off",
                      "controller power off"]
POWER_ON_KEYWORDS  = ["power on", "powered on", "turning on",
                      "bluetooth on", "enabled", "power state on",
                      "controller power on"]

CSV_OUTPUT    = "bt_timestamps_auto_macos.csv"
POLL_INTERVAL = 0.05    # 50ms polling

# Number of trials to run automatically
NUM_TRIALS = 10

# Seconds to wait between trials (lets Bluetooth stabilise)
INTER_TRIAL_PAUSE = 5

# Seconds to wait after power-on before starting next trial
# (ensures adapter is fully ready)
POST_RESTORE_PAUSE = 3

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

# BLUEUTIL

def check_blueutil() -> bool:
    """Return True if blueutil is available."""
    r = subprocess.run(["which", "blueutil"],
                       capture_output=True, text=True)
    return r.returncode == 0

def bt_power(on: bool) -> bool:
    """
    Toggle Bluetooth on (True) or off (False) using blueutil.
    Returns True on success.
    """
    val = "1" if on else "0"
    r = subprocess.run(
        ["blueutil", "--power", val],
        capture_output=True, text=True, timeout=10
    )
    return r.returncode == 0

def bt_is_on() -> bool:
    """Return current Bluetooth power state."""
    r = subprocess.run(["blueutil", "--power"],
                       capture_output=True, text=True, timeout=5)
    return r.stdout.strip() == "1"

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
                for ts_key in ("LastSeenTime", "LastConnected",
                               "LastConnectedTime"):
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
        m = re.match(
            r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)[+-]\d{4}",
            line
        )
        if m:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")
            return dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None

def classify_log_line(line: str) -> str | None:
    lower = line.lower()
    if any(k in lower for k in POWER_OFF_KEYWORDS):
        return "power_off"
    if any(k in lower for k in POWER_ON_KEYWORDS):
        return "power_on"
    # Fallback — any BT activity after our T1 is relevant
    if "bluetooth" in lower or "bthd" in lower:
        return "bt_activity"
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
                "label":       f"BT_{ev_type.upper()} (Unified Log)",
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

    def wait_for_change(self, timeout: int = 30) -> bool:
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
        return (f"Unified Log {direction} system clock by ~1h "
                "| UTC+1 timezone misconfiguration?")
    elif 7190_000 <= abs(skew_ms) <= 7210_000:
        return (f"Unified Log {direction} system clock by ~2h "
                "| UTC+2 timezone misconfiguration?")
    else:
        return (f"Unified Log {direction} system clock by "
                f"{abs_s:.1f}s | check system time settings")

# ─── CSV ────

CSV_HEADERS = [
    "trial",
    "event_type",
    "T1_blueutil_call_UTC",
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

# ─── SINGLE TRIAL ─────────────────────────────────────────────────────────────

def run_trial(trial: int, plist_watcher: PlistWatcher,
              notes: str = "") -> dict | None:
    """
    Run one automated trial:
      1. Reset plist watcher
      2. Call blueutil --power 0, record T1
      3. Watch plist + Unified Log in parallel
      4. Record T2, T3, T4
      5. Restore Bluetooth (blueutil --power 1)
      6. Return result dict
    """
    print(f"\n  TRIAL {trial}")
    print("  " + "─" * 40)

    # Reset plist watcher
    plist_watcher.reset()

    # ── Step 1: toggle Bluetooth OFF — record T1 ──
    print("  Calling blueutil --power 0 ...", end=" ", flush=True)
    T1 = now_utc()
    success = bt_power(False)
    T1_end  = now_utc()  # how long the call itself took

    call_duration = delta_ms(T1, T1_end)
    if not success:
        print("FAILED")
        print("  [!] blueutil returned non-zero. Skipping trial.")
        bt_power(True)
        return None
    print(f"OK  (call took {call_duration:.1f} ms)")
    print(f"  T1 (blueutil call): {fmt(T1)}")
    print("  Watching plist + Unified Log... (timeout: 30s)")

    # ── Step 2: parallel watchers ──
    log_result_holder = [None]
    log_done_event    = threading.Event()

    def log_thread_fn():
        deadline = time.time() + 30
        while time.time() < deadline:
            result = query_unified_log_once(T1)
            if result:
                log_result_holder[0] = result
                break
            time.sleep(POLL_INTERVAL)
        log_done_event.set()

    threading.Thread(target=log_thread_fn, daemon=True).start()

    changed  = plist_watcher.wait_for_change(timeout=30)
    T3       = plist_watcher.change_time
    T4_mtime = plist_watcher.change_mtime

    log_done_event.wait(timeout=30)
    log_result = log_result_holder[0]

    # ── Step 3: restore Bluetooth ──
    print("  Restoring Bluetooth (blueutil --power 1) ...", end=" ", flush=True)
    bt_power(True)
    print("OK")

    # ── Step 4: read embedded plist timestamp ──
    plist_device_name, T4_value = read_plist_last_seen()

    if not changed and log_result is None:
        print("  [!] No plist change and no log entry detected.")
        print("      The Bluetooth toggle may not have generated expected events.")
        return None

    T2 = log_result["T2_log_time"] if log_result else None

    # Clock skew
    if T2 and T3:
        skew_ms   = delta_ms(T3, T2)
        skew_desc = describe_skew(skew_ms)
    else:
        skew_ms   = None
        skew_desc = "could not measure — T2 or T3 missing"

    # Deltas
    d_T2_T1  = delta_ms(T1, T2)        if T2       else None
    d_T3_T1  = delta_ms(T1, T3)        if T3       else None
    d_T4m_T1 = delta_ms(T1, T4_mtime)  if T4_mtime else None
    d_T4v_T1 = delta_ms(T1, T4_value)  if T4_value else None

    label = (log_result["label"] if log_result
             else ("PLIST CHANGE (no log entry)" if changed else "NO EVENT"))

    # Print results
    print(f"  Event type: {label}")
    print(f"  T1 (blueutil call):         {fmt(T1)}")
    print(f"  T2 (Unified Log):           {fmt(T2)       if T2       else 'not found'}")
    print(f"  T3 (plist detected):        {fmt(T3)       if T3       else 'not detected'}")
    print(f"  T4 (plist mtime):           {fmt(T4_mtime) if T4_mtime else 'n/a'}")
    print(f"  T4v(plist LastSeen value):  {fmt(T4_value) if T4_value else 'n/a'}"
          + (f"  [{plist_device_name}]" if plist_device_name else ""))

    print(f"\n  ── Deltas (pure OS latency — no human delay) ───────")
    if d_T2_T1  is not None: print(f"  T2 - T1  Unified Log delay:    {d_T2_T1:>10.2f} ms")
    if d_T3_T1  is not None: print(f"  T3 - T1  plist detection:      {d_T3_T1:>10.2f} ms")
    if d_T4m_T1 is not None: print(f"  T4m- T1  plist mtime delay:    {d_T4m_T1:>10.2f} ms")
    if d_T4v_T1 is not None: print(f"  T4v- T1  LastSeen value delay: {d_T4v_T1:>10.2f} ms")
    if skew_ms  is not None: print(f"  Skew     T2 - T3:             {skew_ms:>+10.2f} ms")

    t2_str  = f"{d_T2_T1:.1f} ms"  if d_T2_T1  is not None else "n/a"
    t3_str  = f"{d_T3_T1:.1f} ms"  if d_T3_T1  is not None else "n/a"
    t4m_str = f"{d_T4m_T1:.1f} ms" if d_T4m_T1 is not None else "n/a"
    t4v_str = f"{d_T4v_T1:.1f} ms" if d_T4v_T1 is not None else "n/a"
    sk_str  = f"{skew_ms/1000:+.3f}s" if skew_ms is not None else "n/a"

    print(f"\n  ┌─────────────────────────────────────────────────┐")
    print(f"  │  FORENSIC FINDING — Trial {trial:<3}                    │")
    print(f"  │  Unified Log delay:  {t2_str:<30}│")
    print(f"  │  Plist detection:    {t3_str:<30}│")
    print(f"  │  Plist mtime delay:  {t4m_str:<30}│")
    print(f"  │  LastSeen accuracy:  {t4v_str:<30}│")
    print(f"  │  Clock skew:         {sk_str:<30}│")
    print(f"  └─────────────────────────────────────────────────┘")

    return {
        "trial":                      trial,
        "event_type":                 label,
        "T1_blueutil_call_UTC":       fmt(T1),
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

# MAIN 

def main():
    print("=" * 62)
    print("  Bluetooth Timestamp Triangulation — macOS Automated")
    print("  Stockholm University — CYFO Assignment")
    print("=" * 62)
    print()
    print(f"  Trials:             {NUM_TRIALS}")
    print(f"  Inter-trial pause:  {INTER_TRIAL_PAUSE}s")
    print(f"  Post-restore pause: {POST_RESTORE_PAUSE}s")
    print(f"  Output CSV:         {CSV_OUTPUT}")
    print()

    # ── Dependency checks ──
    if not check_blueutil():
        print("  [!] blueutil not found.")
        print()
        print("  Install it with:")
        print("      brew install blueutil")
        print()
        print("  If Homebrew is not installed:")
        print("      /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com"
              "/Homebrew/install/HEAD/install.sh)\"")
        sys.exit(1)
    print("  [OK] blueutil found")

    r = subprocess.run(["which", "log"], capture_output=True, text=True)
    if r.returncode != 0:
        print("  [!] 'log' CLI not found — macOS 10.12+ required.")
        sys.exit(1)
    print(f"  [OK] log CLI:   {r.stdout.strip()}")

    r2 = subprocess.run(["which", "plutil"], capture_output=True, text=True)
    if r2.returncode != 0:
        print("  [!] 'plutil' not found — plist reading will be skipped.")
    else:
        print(f"  [OK] plutil:    {r2.stdout.strip()}")

    if not os.path.exists(PLIST_PATH):
        print(f"  [!] Plist not found: {PLIST_PATH}")
        print("      Make sure Bluetooth is on and a device has been paired.")
    else:
        print(f"  [OK] Plist:     {PLIST_PATH}")

    # ── Check current BT state ──
    print()
    if not bt_is_on():
        print("  [!] Bluetooth is currently OFF.")
        print("      Turning it on before starting...")
        bt_power(True)
        time.sleep(POST_RESTORE_PAUSE)
        print("  [OK] Bluetooth restored.")

    print()
    print("  NOTE: This script toggles Bluetooth OFF then ON for each trial.")
    print("  All connected BT devices will briefly disconnect.")
    print("  Do not use a Bluetooth keyboard/mouse as your only input device.")
    print()

    confirm = input("  Ready to run? [Y/n]: ").strip().lower()
    if confirm == "n":
        print("  Aborted.")
        sys.exit(0)

    # ── Setup ──
    plist_watcher = PlistWatcher()
    plist_watcher.start()
    print("\n  [OK] Plist watcher started (50ms polling).")
    print("  Starting automated trials...\n")

    completed = 0
    skipped   = 0

    for trial_num in range(1, NUM_TRIALS + 1):

        # Optional per-trial notes at start of each run
        # (comment out the next two lines to run fully unattended)
        notes = ""
        # notes = input(f"\n  Notes for trial {trial_num} [Enter to skip]: ").strip()

        result = run_trial(trial_num, plist_watcher, notes)

        if result is not None:
            write_csv_row(result)
            print(f"\n  Saved → {CSV_OUTPUT}")
            completed += 1
        else:
            skipped += 1
            print(f"  Trial {trial_num} skipped.")

        # Inter-trial pause — let BT adapter stabilise
        if trial_num < NUM_TRIALS:
            print(f"\n  Waiting {INTER_TRIAL_PAUSE}s before next trial...")
            time.sleep(INTER_TRIAL_PAUSE)
            # Ensure BT is on before next trial
            if not bt_is_on():
                print("  [!] Bluetooth still off — waiting extra 2s...")
                time.sleep(2)
                bt_power(True)
                time.sleep(POST_RESTORE_PAUSE)

    plist_watcher.stop()

    # ── Summary ──
    print(f"\n{'=' * 62}")
    print(f"  Done. {completed} trials saved, {skipped} skipped.")
    print(f"  Output: {CSV_OUTPUT}")
    print(f"{'=' * 62}")
    print()
    print("── Column Guide ────────────────────────────────────────────")
    print()
    print("  delta_T2_minus_T1_ms      Unified Log write latency")
    print("  delta_T3_minus_T1_ms      plist detection latency")
    print("  delta_T4_mtime_minus_T1   plist filesystem write delay")
    print("  delta_T4_value_minus_T1   LastSeen embedded value accuracy")
    print("  skew_T2_minus_T3_ms       Unified Log vs system clock")
    print()
    print("  All deltas are PURE OS latency — no human delay included.")
    print("  This makes these measurements more accurate than the")
    print("  manual Windows experiments.")
    print()
    print("── Key configuration ───────────────────────────────────────")
    print(f"  NUM_TRIALS            = {NUM_TRIALS}")
    print(f"  INTER_TRIAL_PAUSE     = {INTER_TRIAL_PAUSE}s")
    print(f"  PRE_T1_COUNTDOWN      = n/a (fully automated)")
    print("─" * 62)

if __name__ == "__main__":
    main()
