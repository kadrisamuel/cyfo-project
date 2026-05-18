#!/usr/bin/env python3
"""
bt_timestamp_compare_macos.py
Bluetooth Timestamp Triangulation Tool — macOS Edition
Stockholm University — Forensic Research

Ported from bt_timestamp_compare_windows_v7.py.

Replacement map (Windows → macOS):
  win32evtlog (BTHUSB Event Log)  → Unified Log  (log show / log stream)
  win32evtlogutil                 → subprocess + log CLI
  winsound.Beep()                 → afplay /System/Library/Sounds/Ping.aiff
  HKLM registry last-write time  → plist file mtime (os.path.getmtime)
  pytime_to_utc()                 → datetime.strptime on log output
  Event ID 8  (paired)            → Unified Log "connected" / "paired" entries
  Event ID 10 (removed)          → Unified Log "removed" / "forget" entries
  UTC+2 clock skew                → macOS Unified Log uses UTC natively
                                    (skew expected near zero)

Timestamps captured per trial:
  T1 - Ground truth:    moment of beep (system clock, UTC)
  T2 - Unified Log:     timestamp recorded inside the log entry
  T3 - plist detection: moment script noticed plist file change
  T4 - plist mtime:     filesystem write time of com.apple.Bluetooth.plist
  T4v- plist value:     LastSeenTime value embedded inside the plist

Key columns in CSV:
  calibrated_delay_ms  — TRUE OS log write delay (T3-T1 minus reaction time)
  t4_plist_delay_ms    — plist file write delay  (T4-T1 minus reaction time)
  skew_T2_minus_T3_ms  — Unified Log vs system clock (should be ~0 on macOS)

Usage:
    python3 bt_timestamp_compare_macos.py

Requirements:
    macOS 13+ (Ventura/Sonoma/Sequoia/Tahoe), Python 3.10+
    No pip dependencies — stdlib + macOS system tools only
    Run as normal user.
    For /Library/Preferences/com.apple.Bluetooth.plist (system-level),
    run with: sudo python3 bt_timestamp_compare_macos.py
"""

import sys
import os
import csv
import time
import subprocess
import threading
import random
import json
import re
from datetime import datetime, timezone, timedelta

# CONFIG
# Bluetooth plist — user-level (no sudo required)
PLIST_PATH = os.path.expanduser("~/Library/Preferences/com.apple.Bluetooth.plist")

# Unified Log predicate for Bluetooth subsystem
BT_LOG_PREDICATE = 'subsystem == "com.apple.bluetooth"'

# Keywords that indicate connection/pairing in Unified Log entries
PAIR_KEYWORDS   = ["connected", "paired", "link key created",
                   "bonded", "connection complete", "hid device added"]
REMOVE_KEYWORDS = ["removed", "forget", "unpaired", "link key deleted",
                   "device deleted", "removing device"]

CSV_OUTPUT      = "bt_timestamps_macos.csv"
CSV_CALIBRATION = "bt_calibration_macos.csv"
POLL_INTERVAL   = 0.05   # 50ms

CALIBRATION_TRIALS         = 5
PRE_BEEP_COUNTDOWN_SECONDS = 5

# Apple Cocoa epoch — timestamps in plist are seconds since Jan 1 2001 UTC
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

def cocoa_to_utc(cocoa_ts: float) -> datetime:
    """Convert Apple Cocoa epoch timestamp to UTC datetime."""
    return COCOA_EPOCH + timedelta(seconds=float(cocoa_ts))

def mean(values: list) -> float:
    return sum(values) / len(values)

def stdev(values: list) -> float:
    m = mean(values)
    return (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5

# AUDIO BEEP
def beep():
    """Play a short system beep using afplay (no dependencies)."""
    sounds = [
        "/System/Library/Sounds/Ping.aiff",
        "/System/Library/Sounds/Tink.aiff",
        "/System/Library/Sounds/Pop.aiff",
        "/System/Library/Sounds/Morse.aiff",
    ]
    for sound in sounds:
        if os.path.exists(sound):
            subprocess.Popen(
                ["afplay", sound],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return
    # Fallback: terminal bell
    print("\a", end="", flush=True)

def countdown(seconds: int) -> datetime:
    """Print live countdown, then beep. Returns exact beep time as T1."""
    if seconds <= 0:
        T1 = now_utc()
        beep()
        return T1
    print(f"\n  Get your mouse over the button — beep in {seconds}s...")
    for i in range(seconds, 0, -1):
        print(f"  {i}...", end="\r", flush=True)
        time.sleep(1)
    print("  " + " " * 20, end="\r")
    T1 = now_utc()
    beep()
    return T1

# PLIST HELPERS
def get_plist_mtime() -> datetime | None:
    """Return filesystem modification time of the Bluetooth plist."""
    try:
        mtime = os.path.getmtime(PLIST_PATH)
        return datetime.fromtimestamp(mtime, tz=timezone.utc)
    except Exception:
        return None

def read_plist_last_seen() -> tuple:
    """
    Read the Bluetooth plist and return the most recently updated
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
    """
    Parse the leading timestamp from a 'log show --style compact' line.
    Format: YYYY-MM-DD HH:MM:SS.ffffff+0000
    """
    try:
        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)[+-]\d{4}", line)
        if m:
            dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f")
            return dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None

def classify_log_line(line: str) -> str | None:
    """Return 'paired', 'removed', or None based on log line content."""
    lower = line.lower()
    if any(k in lower for k in PAIR_KEYWORDS):
        return "paired"
    if any(k in lower for k in REMOVE_KEYWORDS):
        return "removed"
    return None

def query_unified_log_once(since: datetime) -> dict | None:
    """
    Run one 'log show' query for Bluetooth events after `since`.
    Returns the first matching event dict or None.
    """
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    try:
        r = subprocess.run(
            [
                "log", "show",
                "--predicate", BT_LOG_PREDICATE,
                "--info",
                "--start", since_str,
                "--style", "compact",
            ],
            capture_output=True, text=True, timeout=10
        )
        lines = [
            l for l in r.stdout.splitlines()
            if l.strip() and not l.startswith("Filtering")
        ]
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
                "event_type":  ev_type,
            }
    except Exception as e:
        print(f"  [!] Log query error: {e}")
    return None

# PLIST WATCHER
class PlistWatcher:
    """
    Polls com.apple.Bluetooth.plist mtime every POLL_INTERVAL seconds.
    Records T3 — the moment our script detects a file change.
    Also records T4 — the file's modification timestamp at that moment.
    This is the macOS equivalent of the Windows registry write-time watcher.
    """

    def __init__(self):
        self.last_mtime: datetime | None = get_plist_mtime()
        self.change_time: datetime | None  = None   # T3: when WE noticed it
        self.change_mtime: datetime | None = None   # T4: filesystem mtime
        self._trigger = threading.Event()
        self._running = False

    def start(self):
        self._running = True
        t = threading.Thread(target=self._poll, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def reset(self):
        self.last_mtime   = get_plist_mtime()
        self.change_time  = None
        self.change_mtime = None
        self._trigger.clear()

    def wait_for_change(self, timeout: int = 60) -> bool:
        """Block until plist changes or timeout. Returns True if changed."""
        return self._trigger.wait(timeout=timeout)

    def _poll(self):
        while self._running:
            time.sleep(POLL_INTERVAL)
            if self._trigger.is_set():
                continue
            try:
                mtime = get_plist_mtime()
                if mtime and self.last_mtime and mtime != self.last_mtime:
                    self.change_time  = now_utc()   # T3: system clock NOW
                    self.change_mtime = mtime        # T4: actual file mtime
                    self.last_mtime   = mtime
                    self._trigger.set()
            except Exception:
                pass

# CLOCK SKEW
def skew_from_live_event(T2: datetime, T3: datetime) -> float:
    """
    Skew = T2 - T3. On macOS, Unified Log uses UTC natively so skew
    should be near zero. A large skew indicates a real clock problem.
    """
    return delta_ms(T3, T2)

def describe_skew(skew_ms: float) -> str:
    abs_s = abs(skew_ms) / 1000
    direction = "ahead of" if skew_ms > 0 else "behind"
    if abs(skew_ms) < 500:
        return "clocks aligned — Unified Log using UTC correctly"
    elif 3590_000 <= abs(skew_ms) <= 3610_000:
        return (f"Unified Log clock {direction} system clock by ~1h "
                "| possible timezone misconfiguration (UTC+1?)")
    elif 7190_000 <= abs(skew_ms) <= 7210_000:
        return (f"Unified Log clock {direction} system clock by ~2h "
                "| possible timezone misconfiguration (UTC+2?)")
    else:
        return (f"Unified Log clock {direction} system clock by {abs_s:.1f}s "
                "| investigate system time settings")

# REACTION TIME CALIBRATION
def run_calibration() -> tuple:
    """
    Measure user reaction time over CALIBRATION_TRIALS trials.
    Returns (mean_ms, stdev_ms).
    """
    print()
    print("── Reaction Time Calibration ───────────────────────────────")
    print()
    print("  Measures YOUR reaction time so it can be subtracted")
    print("  from results, isolating the true OS write delay.")
    print()
    print(f"  • Keep your finger hovering over Enter")
    print(f"  • The moment you hear a BEEP, press Enter")
    print(f"  • {CALIBRATION_TRIALS} trials — random wait prevents anticipation")
    print()
    input("  Press Enter when ready...\n")

    times = []
    i = 1
    while i <= CALIBRATION_TRIALS:
        print(f"  Trial {i}/{CALIBRATION_TRIALS} — get ready...")
        time.sleep(random.uniform(2.0, 4.0))

        T_beep = now_utc()
        beep()
        input()
        T_press = now_utc()

        rt = delta_ms(T_beep, T_press)

        if rt > 2000:
            print(f"  [!] {rt:.0f} ms — too slow, retrying.")
            continue

        times.append(rt)
        print(f"  Reaction time: {rt:.1f} ms")
        i += 1

    mean_rt = mean(times)
    std_rt  = stdev(times) if len(times) > 1 else 0.0

    print()
    print(f"  Individual times: {[round(t,1) for t in times]} ms")
    print(f"  Mean:  {mean_rt:.1f} ms")
    print(f"  Stdev: {std_rt:.1f} ms")

    if mean_rt < 100:
        print("  [!] Suspiciously fast — did you press before the beep?")
    elif mean_rt > 600:
        print("  [!] Slow — try with finger resting on Enter key.")
    else:
        print(f"  [OK] Normal. Will subtract {mean_rt:.0f} ms from all T3-T1 values.")

    exists = os.path.exists(CSV_CALIBRATION)
    with open(CSV_CALIBRATION, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["session_UTC", "trial",
                        "reaction_time_ms", "mean_ms", "stdev_ms"])
        ts = fmt(now_utc())
        for idx, rt in enumerate(times, 1):
            w.writerow([ts, idx, round(rt,2), round(mean_rt,2), round(std_rt,2)])

    print(f"  Saved → {CSV_CALIBRATION}")
    print("─" * 62)
    return mean_rt, std_rt

# CSV
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
    "corrected_delay_ms",
    "reaction_time_mean_ms",
    "calibrated_delay_ms",
    "t4_plist_delay_ms",
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
    print("  Stockholm University — Forensic Research")
    print("=" * 62)

    # Sanity checks
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
    else:
        print(f"  [OK] log CLI: {r.stdout.strip()}")

    r2 = subprocess.run(["which", "plutil"], capture_output=True, text=True)
    if r2.returncode != 0:
        print("  [!] 'plutil' not found — plist reading will be skipped.")
    else:
        print(f"  [OK] plutil:  {r2.stdout.strip()}")

    # NTP offset check
    try:
        r3 = subprocess.run(
            ["sntp", "-d", "time.apple.com"],
            capture_output=True, text=True, timeout=5
        )
        for line in r3.stdout.splitlines():
            if "offset" in line.lower():
                print(f"  [OK] NTP:     {line.strip()}")
                break
    except Exception:
        print("  [i] NTP check skipped")

    print()

    # Calibration
    mean_rt, std_rt = run_calibration()

    # Setup
    print("\n── Setup ───────────────────────────────────────────────────")
    plist_watcher = PlistWatcher()
    plist_watcher.start()
    mtime = get_plist_mtime()
    print(f"  Plist watcher started (50ms polling)")
    print(f"  Current plist mtime:  {fmt(mtime)}")
    print(f"  Output CSV:           {CSV_OUTPUT}")
    print()
    print("  NOTE: Four timestamps captured per trial (T1–T4)")
    print("  vs three on Windows — T4 (plist mtime + LastSeen value)")
    print("  directly addresses the concept note's research question")
    print("  about plist timestamp accuracy on macOS.")

    # Protocol
    print()
    print("── Trial Protocol ──────────────────────────────────────────")
    print()
    print("  FORGET DEVICE trial (equivalent to Windows ID 10 removal):")
    print("    1. System Settings → Bluetooth → your device")
    print("    2. Click (i) → 'Forget This Device'")
    print("    3. Stop at confirmation popup — do NOT confirm yet")
    print("    4. Press ENTER here — countdown then beep")
    print("    5. On the beep: immediately click 'Forget Device'")
    print()
    print("  PAIRING trial (equivalent to Windows ID 8):")
    print("    1. Forget the device fully first")
    print("    2. Put device into pairing mode")
    print("    3. System Settings → Bluetooth → wait for device to appear")
    print("    4. Do NOT click Connect yet")
    print("    5. Press ENTER here — countdown then beep")
    print("    6. On the beep: immediately click Connect")
    print()
    print(f"  Reaction time correction: {mean_rt:.0f} ms (auto-subtracted)")
    print(f"  Countdown before beep:    {PRE_BEEP_COUNTDOWN_SECONDS}s")
    print("─" * 62)

    trial   = 1
    skew_ms = None

    while True:
        print(f"\n  TRIAL {trial}")
        print("  " + "─" * 40)

        if skew_ms is None:
            print("  [i] Skew unknown — will be measured from this trial.")
        else:
            print(f"  [i] Skew: {skew_ms:+.0f} ms ({skew_ms/1000:+.3f}s) "
                  f"| RT: {mean_rt:.0f} ms")

        notes = input("\n  Notes for this trial [Enter to skip]: ").strip()
        input("\n  >>> Get action ready, press ENTER to start countdown <<<\n")

        # Reset plist watcher BEFORE countdown so we don't miss fast events
        plist_watcher.reset()

        # Countdown → beep → T1
        T1 = countdown(PRE_BEEP_COUNTDOWN_SECONDS)
        print(f"  T1 (beep): {fmt(T1)}")
        print("  Watching plist + Unified Log... (timeout: 60s)")

        # Run Unified Log query in background thread while plist watcher polls
        log_result_holder = [None]
        log_done_event    = threading.Event()

        def log_thread_fn():
            # Poll log every POLL_INTERVAL until event found or timeout
            deadline = time.time() + 60
            while time.time() < deadline:
                result = query_unified_log_once(T1)
                if result:
                    log_result_holder[0] = result
                    break
                time.sleep(POLL_INTERVAL)
            log_done_event.set()

        log_thread = threading.Thread(target=log_thread_fn, daemon=True)
        log_thread.start()

        # Wait for plist change (T3/T4)
        changed = plist_watcher.wait_for_change(timeout=60)
        T3       = plist_watcher.change_time   # system clock when change detected
        T4_mtime = plist_watcher.change_mtime  # filesystem mtime of plist

        # Wait for log thread
        log_done_event.wait(timeout=60)
        log_result = log_result_holder[0]

        # Read embedded plist timestamp
        plist_device_name, T4_value = read_plist_last_seen()

        if not changed and log_result is None:
            print("\n  [!] No plist change and no log entry detected within 60s.")
            print("      Make sure you performed the action on the beep.")
            trial += 1
            cont = input("\n  Try another trial? [Y/n]: ").strip().lower()
            if cont == "n":
                break
            continue

        T2 = log_result["T2_log_time"] if log_result else None

        # Clock skew — only meaningful if both T2 and T3 available
        if T2 and T3:
            skew_ms   = skew_from_live_event(T2, T3)
            skew_desc = describe_skew(skew_ms)
        else:
            skew_desc = "could not measure — T2 or T3 missing"

        # Compute all deltas
        d_T2_T1        = delta_ms(T1, T2)        if T2       else None
        d_T3_T1        = delta_ms(T1, T3)        if T3       else None
        d_T4m_T1       = delta_ms(T1, T4_mtime)  if T4_mtime else None
        d_T4v_T1       = delta_ms(T1, T4_value)  if T4_value else None
        corrected      = (d_T2_T1 - skew_ms)     if (d_T2_T1 is not None
                                                      and skew_ms is not None) else None
        calibrated     = (d_T3_T1 - mean_rt)     if d_T3_T1  is not None else None
        t4_plist_delay = (d_T4m_T1 - mean_rt)    if d_T4m_T1 is not None else None

        label = (log_result["label"] if log_result
                 else ("PLIST CHANGE (no log entry)" if changed else "NO EVENT"))

        # Print results
        print(f"\n  Event type: {label}")
        print(f"  T1 (beep):                  {fmt(T1)}")
        print(f"  T2 (Unified Log):           {fmt(T2) if T2 else 'not found'}")
        print(f"  T3 (plist file detected):   {fmt(T3) if T3 else 'not detected'}")
        print(f"  T4 (plist mtime):           {fmt(T4_mtime) if T4_mtime else 'n/a'}")
        print(f"  T4v(plist LastSeen value):  {fmt(T4_value) if T4_value else 'n/a'}"
              + (f"  [{plist_device_name}]" if plist_device_name else ""))

        print(f"\n  ── Raw Deltas ──────────────────────────────────────")
        if d_T2_T1  is not None: print(f"  T2 - T1  Unified Log delay:      {d_T2_T1:>12.2f} ms")
        if d_T3_T1  is not None: print(f"  T3 - T1  plist detection:        {d_T3_T1:>12.2f} ms")
        if d_T4m_T1 is not None: print(f"  T4m- T1  plist mtime delay:      {d_T4m_T1:>12.2f} ms")
        if d_T4v_T1 is not None: print(f"  T4v- T1  LastSeen value delay:   {d_T4v_T1:>12.2f} ms")

        print(f"\n  ── Skew & Corrections ──────────────────────────────")
        if skew_ms   is not None: print(f"  Skew (T2 - T3):              {skew_ms:>+12.2f} ms")
        if corrected is not None: print(f"  Corrected (T2-T1 - skew):   {corrected:>12.2f} ms")
        print(f"  Reaction time:               {mean_rt:>12.1f} ms")
        if calibrated     is not None:
            print(f"  Calibrated log delay:        {calibrated:>12.2f} ms  ← TRUE log delay")
        if t4_plist_delay is not None:
            print(f"  Plist write delay:           {t4_plist_delay:>12.2f} ms  ← plist latency")

        cal_str = f"{calibrated:.1f} ms"    if calibrated     is not None else "n/a"
        t4_str  = f"{t4_plist_delay:.1f} ms" if t4_plist_delay is not None else "n/a"
        sk_str  = f"{skew_ms/1000:+.3f}s"   if skew_ms        is not None else "n/a"

        print(f"\n  ┌───────────────────────────────────────────────────┐")
        print(f"  │  FORENSIC FINDING — Trial {trial:<3}                      │")
        print(f"  │  Event:              {label:<32}│")
        print(f"  │  Log delay (calib):  {cal_str:<32}│")
        print(f"  │  Plist write delay:  {t4_str:<32}│")
        print(f"  │  Clock skew:         {sk_str:<32}│")
        print(f"  └───────────────────────────────────────────────────┘")

        row = {
            "trial":                      trial,
            "event_type":                 label,
            "T1_ground_truth_UTC":        fmt(T1),
            "T2_unified_log_UTC":         fmt(T2)       if T2       else "",
            "T3_plist_detection_UTC":     fmt(T3)       if T3       else "",
            "T4_plist_mtime_UTC":         fmt(T4_mtime) if T4_mtime else "",
            "T4_plist_last_seen_UTC":     fmt(T4_value) if T4_value else "",
            "delta_T2_minus_T1_ms":       round(d_T2_T1, 2)        if d_T2_T1        is not None else "",
            "delta_T3_minus_T1_ms":       round(d_T3_T1, 2)        if d_T3_T1        is not None else "",
            "delta_T4_mtime_minus_T1_ms": round(d_T4m_T1, 2)       if d_T4m_T1       is not None else "",
            "delta_T4_value_minus_T1_ms": round(d_T4v_T1, 2)       if d_T4v_T1       is not None else "",
            "skew_T2_minus_T3_ms":        round(skew_ms, 2)         if skew_ms        is not None else "",
            "corrected_delay_ms":         round(corrected, 2)        if corrected       is not None else "",
            "reaction_time_mean_ms":      round(mean_rt, 2),
            "calibrated_delay_ms":        round(calibrated, 2)       if calibrated      is not None else "",
            "t4_plist_delay_ms":          round(t4_plist_delay, 2)   if t4_plist_delay  is not None else "",
            "skew_description":           skew_desc,
            "log_entry":                  log_result["description"]  if log_result else "",
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
    print("  calibrated_delay_ms       TRUE OS log write delay  ← headline")
    print("  t4_plist_delay_ms         plist file write delay   ← compare")
    print("  delta_T4_value_minus_T1   LastSeen value accuracy  ← key finding")
    print("  skew_T2_minus_T3_ms       Unified Log vs system clock")
    print("                            (should be ~0ms on macOS)")
    print()
    print("── Key differences from Windows ────────────────────────────")
    print()
    print("  1. FOUR timestamps per trial (T1-T4) vs three on Windows")
    print("     T4 (plist mtime + LastSeen value) is unique to macOS")
    print()
    print("  2. Unified Log is UTC natively — no 2-hour skew expected")
    print("     A near-zero skew_T2_minus_T3_ms confirms correct UTC")
    print()
    print("  3. Two artifact sources compared: Unified Log (T2) vs")
    print("     plist file (T3/T4) — their difference shows which")
    print("     artifact type is more forensically current")
    print()
    print("  4. T4v (LastSeen value inside plist) may differ from T4m")
    print("     (plist filesystem mtime) — this gap is itself a finding")
    print("─" * 62)

if __name__ == "__main__":
    main()
