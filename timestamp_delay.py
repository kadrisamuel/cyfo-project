#!/usr/bin/env python3
"""
bt_timestamp_compare.py
=======================
Bluetooth Timestamp Triangulation Tool for macOS Forensic Research

Captures three timestamps for each Bluetooth connection event:
  T1 - Ground truth: your reference clock (manual input or NTP)
  T2 - Unified Log: when bluetoothd logged the event
  T3 - plist mtime: when macOS wrote the file to disk

Computes deltas between all three and saves results to CSV.

Usage:
    python3 bt_timestamp_compare.py

Requirements:
    macOS with Python 3.8+
    Run as normal user (sudo needed only for system-level plist)
"""

import subprocess
import time
import os
import csv
import threading
import json
import re
from datetime import datetime, timezone, timedelta

# CONFIG 

# Plist to monitor (user-level; no sudo required)
PLIST_PATH = os.path.expanduser("~/Library/Preferences/com.apple.Bluetooth.plist")

# Output CSV file
CSV_OUTPUT = "bt_timestamps.csv"

# How often to poll the plist (seconds)
POLL_INTERVAL = 0.05  # 50ms

# HELPERS 

COCOA_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

def cocoa_to_utc(ts: float) -> datetime:
    return COCOA_EPOCH + timedelta(seconds=float(ts))

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"

def delta_ms(a: datetime, b: datetime) -> float:
    """Return (b - a) in milliseconds."""
    return (b - a).total_seconds() * 1000

def read_plist_json() -> dict:
    """Convert binary plist to JSON dict via plutil."""
    try:
        r = subprocess.run(
            ["plutil", "-convert", "json", "-o", "-", PLIST_PATH],
            capture_output=True, text=True, timeout=3
        )
        return json.loads(r.stdout)
    except Exception:
        return {}

def extract_last_seen(plist_data: dict) -> tuple[str | None, datetime | None]:
    """
    Walk the plist and find the most recently updated LastSeenTime.
    Returns (device_name, utc_datetime) or (None, None).
    """
    latest_ts = None
    latest_name = None

    # Top-level DeviceCache or paired device dict
    for key in ("DeviceCache", "PairedDevices", "KnownDevices"):
        devices = plist_data.get(key, {})
        if isinstance(devices, dict):
            for addr, info in devices.items():
                if not isinstance(info, dict):
                    continue
                for ts_key in ("LastSeenTime", "LastConnected", "LastConnectedTime"):
                    raw = info.get(ts_key)
                    if raw is not None:
                        try:
                            dt = cocoa_to_utc(raw)
                            if latest_ts is None or dt > latest_ts:
                                latest_ts = dt
                                latest_name = info.get("Name", addr)
                        except Exception:
                            pass

    return latest_name, latest_ts

def get_plist_mtime() -> datetime:
    """Return the file system modification time of the plist as UTC datetime."""
    mtime = os.path.getmtime(PLIST_PATH)
    return datetime.fromtimestamp(mtime, tz=timezone.utc)

def query_unified_log(since: datetime, device_hint: str = "") -> datetime | None:
    """
    Query the Unified Log for the most recent Bluetooth connection event
    since `since`. Returns the log entry timestamp or None.
    """
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")
    predicate = 'subsystem == "com.apple.bluetooth"'
    if device_hint:
        predicate += f' && eventMessage contains "{device_hint}"'

    try:
        r = subprocess.run(
            ["log", "show",
             "--predicate", predicate,
             "--info",
             "--start", since_str,
             "--style", "compact"],
            capture_output=True, text=True, timeout=10
        )
        lines = [l for l in r.stdout.splitlines()
                 if l.strip() and not l.startswith("Filtering")]

        # Parse the first timestamp we find that looks like a connection
        connection_keywords = ["connected", "HID", "GATT", "link", "paired"]
        for line in lines:
            if any(kw.lower() in line.lower() for kw in connection_keywords):
                # Compact format: "YYYY-MM-DD HH:MM:SS.ffffff+0000  ..."
                m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)[+-]\d{4}", line)
                if m:
                    ts_str = m.group(1)
                    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
                    return dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    return None

# CSV SETUP

CSV_HEADERS = [
    "trial",
    "device_name",
    "T1_ground_truth_UTC",
    "T2_unified_log_UTC",
    "T3_plist_mtime_UTC",
    "T4_plist_last_seen_UTC",
    "delta_T2_minus_T1_ms",
    "delta_T3_minus_T1_ms",
    "delta_T4_minus_T1_ms",
    "delta_T3_minus_T2_ms",
    "notes",
]

def write_csv_row(row: dict):
    file_exists = os.path.exists(CSV_OUTPUT)
    with open(CSV_OUTPUT, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

# LIVE PLIST WATCHER

class PlistWatcher:
    """Watches the Bluetooth plist for changes and records the moment it changes."""

    def __init__(self):
        self.last_mtime = get_plist_mtime()
        self.change_event = threading.Event()
        self.change_time: datetime | None = None
        self._running = False

    def start(self):
        self._running = True
        t = threading.Thread(target=self._poll, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def reset(self):
        """Call before each trial to clear the previous detection."""
        self.last_mtime = get_plist_mtime()
        self.change_event.clear()
        self.change_time = None

    def wait_for_change(self, timeout=30) -> datetime | None:
        """Block until plist changes or timeout. Returns detected change time."""
        self.change_event.wait(timeout=timeout)
        return self.change_time

    def _poll(self):
        while self._running:
            time.sleep(POLL_INTERVAL)
            try:
                mtime = get_plist_mtime()
                if mtime != self.last_mtime:
                    self.change_time = now_utc()  # Record NOW as T3
                    self.last_mtime = mtime
                    self.change_event.set()
            except Exception:
                pass

# MAIN EXPERIMENT LOOP

def main():
    print("=" * 60)
    print("  Bluetooth Timestamp Triangulation Tool")
    print("  Stockholm University — Forensic Research")
    print("=" * 60)
    print(f"\nMonitoring plist: {PLIST_PATH}")
    print(f"Output CSV:       {CSV_OUTPUT}\n")

    if not os.path.exists(PLIST_PATH):
        print(f"ERROR: Plist not found at {PLIST_PATH}")
        print("Make sure Bluetooth is enabled and a device has been paired.")
        return

    watcher = PlistWatcher()
    watcher.start()
    print("Plist watcher started (polling every 50ms).\n")

    trial = 1

    while True:
        print("─" * 60)
        print(f"TRIAL {trial}")
        print("─" * 60)
        print("Steps:")
        print("  1. Look at your reference clock (phone/stopwatch)")
        print("  2. Press ENTER here to mark T1 (ground truth)")
        print("  3. IMMEDIATELY toggle your Bluetooth device on/off")
        print()

        notes = input("Notes for this trial (device name, conditions) [Enter to skip]: ").strip()
        device_hint = input("Device name hint for log search (partial name ok) [Enter to skip]: ").strip()

        input("\n>>> Press ENTER to mark T1 and start monitoring... <<<")

        # T1: Ground truth — the moment the user marks the event
        T1 = now_utc()
        print(f"\nT1 (ground truth): {fmt(T1)}")
        print("Now toggle your Bluetooth device. Waiting for plist change...")

        watcher.reset()

        # T3: plist filesystem mtime change
        T3 = watcher.wait_for_change(timeout=30)

        if T3 is None:
            print("No plist change detected within 30s. Skipping trial.")
            continue

        print(f"T3 (plist mtime):  {fmt(T3)}")

        # T4: LastSeenTime value embedded inside the plist
        plist_data = read_plist_json()
        device_name, T4 = extract_last_seen(plist_data)
        if T4:
            print(f"T4 (plist value):  {fmt(T4)}  [{device_name}]")
        else:
            print("T4 (plist value):  not found")

        # T2: Unified Log entry timestamp (query last 2 minutes)
        log_since = T1 - timedelta(seconds=5)
        print("Querying Unified Log for connection entry...")
        T2 = query_unified_log(log_since, device_hint)
        if T2:
            print(f"T2 (unified log):  {fmt(T2)}")
        else:
            print("T2 (unified log):  no matching entry found")

        # Compute deltas
        print("\n Deltas")
        row = {
            "trial": trial,
            "device_name": device_name or device_hint or "unknown",
            "T1_ground_truth_UTC": fmt(T1),
            "T2_unified_log_UTC": fmt(T2) if T2 else "",
            "T3_plist_mtime_UTC": fmt(T3),
            "T4_plist_last_seen_UTC": fmt(T4) if T4 else "",
            "delta_T2_minus_T1_ms": round(delta_ms(T1, T2), 2) if T2 else "",
            "delta_T3_minus_T1_ms": round(delta_ms(T1, T3), 2),
            "delta_T4_minus_T1_ms": round(delta_ms(T1, T4), 2) if T4 else "",
            "delta_T3_minus_T2_ms": round(delta_ms(T2, T3), 2) if T2 else "",
            "notes": notes,
        }

        if T2:
            print(f"  T2 - T1 (log delay):         {row['delta_T2_minus_T1_ms']:>10.2f} ms")
        print(f"  T3 - T1 (plist write delay): {row['delta_T3_minus_T1_ms']:>10.2f} ms")
        if T4:
            print(f"  T4 - T1 (embedded ts delay): {row['delta_T4_minus_T1_ms']:>10.2f} ms")
        if T2:
            print(f"  T3 - T2 (write vs log gap):  {row['delta_T3_minus_T2_ms']:>10.2f} ms")

        write_csv_row(row)
        print(f"\nSaved to {CSV_OUTPUT}")

        trial += 1
        cont = input("\nRun another trial? [Y/n]: ").strip().lower()
        if cont == "n":
            break

    print(f"\nDone. {trial - 1} trials saved to {CSV_OUTPUT}")
    print("Open the CSV in Excel or Numbers to compute mean/std of each delta column.")

if __name__ == "__main__":
    main()
