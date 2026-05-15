#!/usr/bin/env python3
"""
Bluetooth Timestamp Triangulation Tool for Windows 11

Timestamps captured per trial:
  T1 - Ground truth:  moment of beep (system clock, UTC)
  T2 - Event Log:     timestamp Windows assigned to the BTHUSB event
  T3 - Detection:     moment script first noticed the new log entry

Key columns in CSV:
  calibrated_delay_ms  — TRUE OS write delay (T3-T1 minus reaction time)
  skew_T2_minus_T3_ms  — Event Log vs system clock offset
  corrected_delay_ms   — T2-T1 minus skew (cross-check)

Usage:
    python bt_timestamp_compare_windows_v7.py

Requirements:
    Windows 11, Python 3.8+
    pip install pywin32
    Run as ADMINISTRATOR (right-click CMD → Run as administrator)
"""

import sys
import os
import csv
import time
import ctypes
import threading
import random
from datetime import datetime, timezone, timedelta

# DEPENDENCY CHECK
try:
    import win32evtlog
    import win32evtlogutil
    import winsound
except ImportError:
    print("Missing dependency. Run:  pip install pywin32")
    sys.exit(1)

# CONFIG
EVENT_LOG_NAME  = "System"
EVENT_SOURCE    = "BTHUSB"
EVENT_ID_PAIR   = 8
EVENT_ID_REMOVE = 10
WATCH_EVENT_IDS = {EVENT_ID_PAIR, EVENT_ID_REMOVE}

EVENT_ID_LABELS = {
    EVENT_ID_PAIR:   "PAIRED   (ID 8)",
    EVENT_ID_REMOVE: "REMOVED  (ID 10)",
}

CSV_OUTPUT      = "bt_timestamps.csv"
CSV_CALIBRATION = "bt_calibration.csv"
POLL_INTERVAL   = 0.05   # 50ms

CALIBRATION_TRIALS = 5
BEEP_FREQUENCY_HZ  = 1000
BEEP_DURATION_MS   = 100

# Seconds of countdown before the beep fires in each trial.
# Use this time to move your mouse over the confirmation button.
# Set to 0 to disable.
PRE_BEEP_COUNTDOWN_SECONDS = 5

# HELPERS
def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def fmt(dt: datetime) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

def delta_ms(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() * 1000

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def pytime_to_utc(pytime) -> datetime:
    return datetime(
        pytime.year, pytime.month, pytime.day,
        pytime.hour, pytime.minute, pytime.second,
        tzinfo=timezone.utc
    )

def beep():
    winsound.Beep(BEEP_FREQUENCY_HZ, BEEP_DURATION_MS)

def countdown(seconds: int):
    """Print a live countdown, then beep. Returns the exact beep time."""
    if seconds <= 0:
        T1 = now_utc()
        beep()
        return T1
    print(f"\n  Get your mouse over the button — beep in {seconds}s...")
    for i in range(seconds, 0, -1):
        print(f"  {i}...", end="\r", flush=True)
        time.sleep(1)
    print("  " + " " * 20, end="\r")  # clear countdown line
    T1 = now_utc()
    beep()
    return T1

def mean(values: list[float]) -> float:
    return sum(values) / len(values)

def stdev(values: list[float]) -> float:
    m = mean(values)
    return (sum((v - m) ** 2 for v in values) / len(values)) ** 0.5

# EVENT LOG HELPERS
def read_recent_bthusb_events(since_log_time: datetime) -> list[dict]:
    """
    Read System Event Log backwards and return all BTHUSB events
    (ID 8 or 10) with T2 strictly greater than since_log_time.
    since_log_time MUST be in Event Log clock time (e.g. UTC+2).
    Returns oldest-first.
    """
    results = []
    try:
        handle = win32evtlog.OpenEventLog(None, EVENT_LOG_NAME)
        flags = (win32evtlog.EVENTLOG_BACKWARDS_READ |
                 win32evtlog.EVENTLOG_SEQUENTIAL_READ)
        events = win32evtlog.ReadEventLog(handle, flags, 0)

        while events:
            for ev in events:
                try:
                    ev_time = pytime_to_utc(ev.TimeGenerated)
                except Exception:
                    continue

                # Both ev_time and since_log_time are in Event Log clock
                if ev_time <= since_log_time:
                    win32evtlog.CloseEventLog(handle)
                    return list(reversed(results))

                raw_id = ev.EventID & 0xFFFF
                source = ev.SourceName or ""

                if source == EVENT_SOURCE and raw_id in WATCH_EVENT_IDS:
                    try:
                        desc = win32evtlogutil.SafeFormatMessage(
                            ev, EVENT_LOG_NAME).strip()
                    except Exception:
                        desc = "(could not format message)"

                    results.append({
                        "event_id":    raw_id,
                        "label":       EVENT_ID_LABELS.get(raw_id, str(raw_id)),
                        "T2_log_time": ev_time,
                        "description": desc,
                    })

            events = win32evtlog.ReadEventLog(handle, flags, 0)

        win32evtlog.CloseEventLog(handle)
    except Exception as e:
        print(f"  [!] Event log read error: {e}")

    return list(reversed(results))


def get_latest_bthusb_event_time() -> datetime | None:
    """
    Return the T2 timestamp of the most recent BTHUSB event.
    This is in Event Log clock time — use directly as anchor.
    """
    try:
        handle = win32evtlog.OpenEventLog(None, EVENT_LOG_NAME)
        flags = (win32evtlog.EVENTLOG_BACKWARDS_READ |
                 win32evtlog.EVENTLOG_SEQUENTIAL_READ)
        events = win32evtlog.ReadEventLog(handle, flags, 0)

        while events:
            for ev in events:
                raw_id = ev.EventID & 0xFFFF
                source = ev.SourceName or ""
                if source == EVENT_SOURCE and raw_id in WATCH_EVENT_IDS:
                    win32evtlog.CloseEventLog(handle)
                    return pytime_to_utc(ev.TimeGenerated)
            events = win32evtlog.ReadEventLog(handle, flags, 0)

        win32evtlog.CloseEventLog(handle)
    except Exception as e:
        print(f"  [!] Anchor read error: {e}")
    return None

# CLOCK SKEW
def skew_from_live_event(T2: datetime, T3: datetime) -> float:
    """
    Skew = T2 - T3 (both from same real-world moment).
    Positive = Event Log clock is ahead of system clock.
    """
    return delta_ms(T3, T2)


def describe_skew(skew_ms: float) -> str:
    hours     = int(abs(skew_ms) // 3_600_000)
    minutes   = int((abs(skew_ms) % 3_600_000) // 60_000)
    seconds   = (abs(skew_ms) % 60_000) / 1000
    direction = "ahead of" if skew_ms > 0 else "behind"

    if 7190_000 <= abs(skew_ms) <= 7210_000:
        cause = "Event Log storing local time (UTC+2, Stockholm)"
    elif 3590_000 <= abs(skew_ms) <= 3610_000:
        cause = "Event Log storing local time (UTC+1)"
    elif abs(skew_ms) < 1000:
        cause = "clocks aligned"
    else:
        cause = "unknown — check Windows time settings"

    return (f"Event Log clock {direction} system clock by "
            f"{hours}h {minutes}m {seconds:.1f}s | {cause}")

# REACTION TIME CALIBRATION
def run_calibration() -> tuple[float, float]:
    """
    Measure user reaction time. Returns (mean_ms, stdev_ms).
    Protocol: random wait → beep → user presses Enter.
    """
    print()
    print("── Reaction Time Calibration ───────────────────────────────")
    print()
    print("  Measures YOUR reaction time so it can be subtracted from")
    print("  results, isolating the true OS write delay.")
    print()
    print("  • Keep your finger hovering over Enter")
    print("  • The moment you hear a BEEP, press Enter")
    print(f"  • {CALIBRATION_TRIALS} trials")
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
        print("  [!] Slow — try again with finger resting on Enter.")
    else:
        print(f"  [OK] Normal reaction time. Will subtract {mean_rt:.0f} ms from results.")

    # Save calibration
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

# EVENT WATCHER
class BTEventWatcher:
    """
    Polls the Event Log for new BTHUSB events.
    IMPORTANT: self.since is always in EVENT LOG clock time,
    not system clock time. This prevents the 2-hour skew from
    causing old events to pass the since-filter.
    """

    def __init__(self, initial_anchor_log_time: datetime):
        # Anchor stored in Event Log clock time
        self.since: datetime = initial_anchor_log_time
        self.found_event: dict | None = None
        self.detect_time: datetime | None = None
        self._trigger = threading.Event()
        self._running = False

    def start(self):
        self._running = True
        t = threading.Thread(target=self._poll, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def reset_with_log_time(self, log_time: datetime):
        """
        Set anchor using a time already in Event Log clock.
        Anchor never moves backwards.
        """
        self.since = max(self.since, log_time)
        self.found_event = None
        self.detect_time = None
        self._trigger.clear()

    def reset_with_system_time(self, system_time: datetime, skew_ms: float):
        """
        Set anchor using system clock time + known skew.
        Converts to Event Log clock time before storing.
        Anchor never moves backwards.
        """
        log_time = system_time + timedelta(milliseconds=skew_ms)
        self.since = max(self.since, log_time)
        self.found_event = None
        self.detect_time = None
        self._trigger.clear()

    def wait_for_event(self, timeout: int = 60) -> dict | None:
        self._trigger.wait(timeout=timeout)
        return self.found_event

    def _poll(self):
        while self._running:
            time.sleep(POLL_INTERVAL)
            if self._trigger.is_set():
                continue
            try:
                # since is in Event Log clock — safe to compare with T2
                events = read_recent_bthusb_events(self.since)
                if events:
                    self.found_event = events[0]
                    self.detect_time = now_utc()  # T3 in system clock
                    self._trigger.set()
            except Exception:
                pass

# CSV
CSV_HEADERS = [
    "trial",
    "event_type",
    "T1_ground_truth_UTC",
    "T2_event_log_UTC",
    "T3_detection_UTC",
    "delta_T2_minus_T1_ms",
    "delta_T3_minus_T1_ms",
    "delta_T3_minus_T2_ms",
    "skew_T2_minus_T3_ms",
    "corrected_delay_ms",
    "reaction_time_mean_ms",
    "calibrated_delay_ms",
    "skew_description",
    "event_description",
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
    print("  Bluetooth Timestamp Triangulation — Windows 11  [v7]")
    print("  Stockholm University — Forensic Research")
    print("=" * 62)

    if not is_admin():
        print("\n[WARNING] Not running as Administrator.")
        print("  Right-click CMD → 'Run as administrator'\n")
    else:
        print("\n[OK] Running as Administrator.")

    # Calibration
    mean_rt, std_rt = run_calibration()

    # Anchor setup
    # Anchor MUST be in Event Log clock time
    print("\n── Anchor Setup ────────────────────────────────────────────")
    latest_log_event_time = get_latest_bthusb_event_time()

    if latest_log_event_time:
        anchor = latest_log_event_time
        print(f"  Anchor (Event Log time): {fmt(anchor)}")
        print(f"  [OK] Using most recent BTHUSB event as anchor.")
    else:
        # No prior BTHUSB events — use a far-future fallback in
        # Event Log time. We add 3 hours to system time to safely
        # exceed the UTC+2 offset on this machine.
        anchor = now_utc() + timedelta(hours=3)
        print(f"  No prior BTHUSB events found.")
        print(f"  Anchor (system+3h fallback): {fmt(anchor)}")
        print(f"  [OK] Will update after first trial.")

    print(f"  Output CSV: {CSV_OUTPUT}\n")

    watcher = BTEventWatcher(initial_anchor_log_time=anchor)
    watcher.start()
    print("[OK] Watcher started (polling every 50ms).")

    # Protocol
    print()
    print("── Trial Protocol ──────────────────────────────────────────")
    print()
    print("  REMOVAL trial (Event ID 10):")
    print("    1. Settings → Bluetooth → mouse → Remove device")
    print("    2. Stop at confirmation popup — do NOT confirm yet")
    print("    3. Press ENTER here — BEEP will sound")
    print("    4. On the beep: immediately click 'Remove device'")
    print()
    print("  PAIRING trial (Event ID 8):")
    print("    1. Remove device fully first")
    print("    2. Put mouse into pairing mode (hold connect button)")
    print("    3. Settings → Bluetooth → Add device → Bluetooth")
    print("    4. Wait until mouse appears — do NOT click yet")
    print("    5. Press ENTER here — BEEP will sound")
    print("    6. On the beep: immediately click your mouse name")
    print()
    print(f"  Reaction time correction: {mean_rt:.0f} ms (auto-subtracted)")
    print(f"  Countdown before beep:    {PRE_BEEP_COUNTDOWN_SECONDS}s (change PRE_BEEP_COUNTDOWN_SECONDS in config)")
    print("─" * 62)

    trial   = 1
    skew_ms = None

    while True:
        print(f"\n  TRIAL {trial}")
        print("  " + "─" * 40)

        if skew_ms is None:
            print("  [i] Skew unknown — will be measured from this trial.")
        else:
            print(f"  [i] Skew: {skew_ms:+.0f} ms ({skew_ms/3_600_000:+.2f}h) "
                  f"| RT: {mean_rt:.0f} ms")

        notes = input("\n  Notes for this trial [Enter to skip]: ").strip()
        input("\n  >>> Get action ready, press ENTER to start countdown <<<\n")

        # Countdown then beep — T1 is the exact moment the beep fires
        T1 = countdown(PRE_BEEP_COUNTDOWN_SECONDS)
        print(f"  T1 (beep): {fmt(T1)}")
        print("  Watching for BTHUSB event... (timeout: 60s)")

        # Set anchor in Event Log time
        if skew_ms is not None:
            # We know the skew — convert T1 to Event Log time
            watcher.reset_with_system_time(T1, skew_ms)
        else:
            # First trial — anchor already set from latest log event
            # Just clear the trigger without moving anchor backwards
            watcher.reset_with_log_time(watcher.since)

        result = watcher.wait_for_event(timeout=60)

        if result is None:
            print("\n  [!] No BTHUSB event detected within 60s.")
            print("      Make sure you completed the remove/pair action.")
            trial += 1
            cont = input("\n  Try another trial? [Y/n]: ").strip().lower()
            if cont == "n":
                break
            continue

        T2 = result["T2_log_time"]   # Event Log clock
        T3 = watcher.detect_time     # system clock

        # Update skew from this live event
        skew_ms   = skew_from_live_event(T2, T3)
        skew_desc = describe_skew(skew_ms)

        # Deltas
        d_T2_T1    = delta_ms(T1, T2)
        d_T3_T1    = delta_ms(T1, T3)
        d_T3_T2    = delta_ms(T2, T3)
        corrected  = d_T2_T1 - skew_ms      # remove clock skew
        calibrated = d_T3_T1 - mean_rt      # remove reaction time

        print(f"\n  Event: {result['label']}")
        print(f"  T1 (beep / ground truth):   {fmt(T1)}")
        print(f"  T2 (Windows log timestamp): {fmt(T2)}")
        print(f"  T3 (script detection):      {fmt(T3)}")

        print(f"\n  ── Raw Deltas ──────────────────────────────────────")
        print(f"  T2 - T1  log timestamp delay:    {d_T2_T1:>12.2f} ms")
        print(f"  T3 - T1  detection latency:      {d_T3_T1:>12.2f} ms")
        print(f"  T3 - T2  write vs claim gap:     {d_T3_T2:>12.2f} ms")

        print(f"\n  ── Skew & Corrections ──────────────────────────────")
        print(f"  Skew (T2 - T3):              {skew_ms:>+12.2f} ms")
        print(f"  Corrected (T2-T1 - skew):   {corrected:>12.2f} ms")
        print(f"  Reaction time (calibrated):  {mean_rt:>12.1f} ms")
        print(f"  Calibrated OS delay:         {calibrated:>12.2f} ms  ← TRUE OS delay")

        print(f"\n  ┌───────────────────────────────────────────────────┐")
        print(f"  │  FORENSIC FINDING — Trial {trial:<3}                      │")
        print(f"  │  Event:            {result['label']:<34}│")
        print(f"  │  True OS delay:    {calibrated:>8.1f} ms                    │")
        print(f"  │  Clock skew:       {skew_ms/3_600_000:>+8.4f} h (UTC+2 local time) │")
        print(f"  └───────────────────────────────────────────────────┘")

        row = {
            "trial":                  trial,
            "event_type":             result["label"],
            "T1_ground_truth_UTC":    fmt(T1),
            "T2_event_log_UTC":       fmt(T2),
            "T3_detection_UTC":       fmt(T3),
            "delta_T2_minus_T1_ms":   round(d_T2_T1, 2),
            "delta_T3_minus_T1_ms":   round(d_T3_T1, 2),
            "delta_T3_minus_T2_ms":   round(d_T3_T2, 2),
            "skew_T2_minus_T3_ms":    round(skew_ms, 2),
            "corrected_delay_ms":     round(corrected, 2),
            "reaction_time_mean_ms":  round(mean_rt, 2),
            "calibrated_delay_ms":    round(calibrated, 2),
            "skew_description":       skew_desc,
            "event_description":      result["description"][:120],
            "notes":                  notes,
        }

        write_csv_row(row)

        # Advance anchor using T2 (already in Event Log time)
        watcher.reset_with_log_time(T2)

        print(f"\n  Saved → {CSV_OUTPUT}")

        trial += 1
        cont = input("\n  Run another trial? [Y/n]: ").strip().lower()
        if cont == "n":
            break

    print(f"\n{'=' * 62}")
    print(f"  Done. {trial - 1} trial(s) saved to {CSV_OUTPUT}")
    print(f"{'=' * 62}")
    print()
    print("── Column Guide ────────────────────────────────────────────")
    print("  calibrated_delay_ms    TRUE OS write delay  ← headline")
    print("  delta_T3_minus_T1_ms   measured latency (RT included)")
    print("  skew_T2_minus_T3_ms    Event Log vs system clock offset")
    print("  corrected_delay_ms     T2-T1 minus skew (cross-check)")
    print()
    print("── Excel ───────────────────────────────────────────────────")
    print("  Filter by event_type, then:")
    print("  =AVERAGE(calibrated_delay_ms)  → mean OS delay per type")
    print("  =STDEV(calibrated_delay_ms)    → consistency")
    print("─" * 62)

if __name__ == "__main__":
    main()
