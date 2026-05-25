#before running this install - pip3 install watchdog matplotlib

import subprocess
import datetime
import time
import os
import csv
import matplotlib.pyplot as plt
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- CONFIGURATION ---
mac_address = 'ac-80-0a-c1-40-56'  # Sony WF-1000XM5
trials = 20
csv_filename = 'unified_drift_results.csv'
graph_filename = 'Forensic_Disk_vs_Log_Drift.png'

def get_path(tool):
    for path in ['/opt/homebrew/bin/', '/usr/local/bin/']:
        if os.path.exists(path + tool):
            return path + tool
    return tool

blueutil_cmd = get_path('blueutil')

# --- WATCHDOG KERNEL EVENT HANDLER ---
class BluetoothFileHandler(FileSystemEventHandler):
    def __init__(self):
        self.plist_flush = None
        self.paired_wal_flush = None
        self.other_wal_flush = None

    def on_modified(self, event):
        # We only care about the exact moment the files are first modified
        if "com.apple.MobileBluetooth.devices.plist" in event.src_path and not self.plist_flush:
            self.plist_flush = datetime.datetime.now()
        elif "com.apple.MobileBluetooth.ledevices.paired.db-wal" in event.src_path and not self.paired_wal_flush:
            self.paired_wal_flush = datetime.datetime.now()
        elif "com.apple.MobileBluetooth.ledevices.other.db-wal" in event.src_path and not self.other_wal_flush:
            self.other_wal_flush = datetime.datetime.now()

print(f'\n=== IEEE Automated Forensic Harness (Kernel Events) ===')
print(f'Target: {mac_address} | Trials: {trials}')
print('=======================================================\n')

valid_trials = []
log_drifts = []
wal_drifts = []

# --- PHASE 1: DATA COLLECTION ---
with open(csv_filename, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow([
        'Trial', 'Trigger Time', 'Log Time', 'Log Drift (s)', 
        'Paired WAL Drift (s)', 'Other WAL Drift (s)', 'Plist Drift (s)'
    ])

    for i in range(1, trials + 1):
        print(f'--- Trial {i}/{trials} ---')
        
        # 1. Reset state
        print('Resetting target endpoint state (disconnecting)...')
        subprocess.run([blueutil_cmd, '--disconnect', mac_address], capture_output=True)
        time.sleep(4) 
        
        # 2. Initialize Watchdog Observer
        event_handler = BluetoothFileHandler()
        observer = Observer()
        # Monitor the entire Bluetooth directory recursively
        observer.schedule(event_handler, '/Library/Bluetooth/', recursive=True)
        observer.start()

        # 3. Start ULS stream
        log_proc = subprocess.Popen(
            ['log', 'stream', '--predicate', 'subsystem == "com.apple.bluetooth"'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(1) 

        # 4. Trigger physical connection
        trigger_time = datetime.datetime.now()
        print(f'[{trigger_time.strftime("%H:%M:%S.%f")}] Injecting programmatic connect trigger...')
        subprocess.run([blueutil_cmd, '--connect', mac_address], capture_output=True)

        # 5. Await log commitment
        print('Awaiting ULS commit event...')
        log_time_str = None
        for line in log_proc.stdout:
            if 'Connection completed' in line or 'Connected' in line or mac_address.upper() in line.upper() or mac_address.lower() in line.lower():
                raw_time = line.split()[0] + ' ' + line.split()[1]
                log_time_str = raw_time.split('+')[0] 
                log_proc.terminate()
                break
        
        # 6. Wait for file flushes (Max 10 seconds to keep loop moving)
        print('Watching kernel events for disk flushes (Timeout: 10s)...')
        timeout_start = time.time()
        while time.time() - timeout_start < 10:
            if event_handler.paired_wal_flush and event_handler.other_wal_flush:
                break
            time.sleep(0.1)

        observer.stop()
        observer.join()

        # 7. Calculate and store
        if log_time_str:
            log_time = datetime.datetime.strptime(log_time_str, "%Y-%m-%d %H:%M:%S.%f")
            log_drift = (log_time - trigger_time).total_seconds()
            
            p_wal_drift = (event_handler.paired_wal_flush - trigger_time).total_seconds() if event_handler.paired_wal_flush else 'N/A'
            o_wal_drift = (event_handler.other_wal_flush - trigger_time).total_seconds() if event_handler.other_wal_flush else 'N/A'
            plist_drift = (event_handler.plist_flush - trigger_time).total_seconds() if event_handler.plist_flush else 'N/A'

            print(f'-> Log Write Delay:    {log_drift:.3f}s')
            print(f'-> Paired WAL Delay:   {p_wal_drift if isinstance(p_wal_drift, str) else f"{p_wal_drift:.3f}s"}')
            print(f'-> Classic Plist:      {plist_drift if isinstance(plist_drift, str) else f"{plist_drift:.3f}s"}\n')
            
            writer.writerow([i, trigger_time.strftime("%Y-%m-%d %H:%M:%S.%f"), log_time_str, round(log_drift, 6), p_wal_drift, o_wal_drift, plist_drift])
            
            valid_trials.append(i)
            log_drifts.append(log_drift)
            
            # For the graph, we will track the paired WAL if it flushed
            if isinstance(p_wal_drift, float):
                wal_drifts.append(p_wal_drift)
            else:
                wal_drifts.append(0) # Fallback if it didn't flush
        else:
            print("Failed to capture log within timeout.\n")

print(f'[+] Phase 1 Complete. Raw data saved to {csv_filename}')

# --- PHASE 2: AUTOMATED GRAPH GENERATION ---
if len(log_drifts) > 0:
    print(f'[+] Phase 2: Generating IEEE-formatted Scatter Plot...')
    
    mean_log = sum(log_drifts) / len(log_drifts)
    
    # Calculate mean WAL drift, excluding missing (0) values
    valid_wals = [w for w in wal_drifts if w > 0]
    mean_wal = sum(valid_wals) / len(valid_wals) if valid_wals else 0

    plt.figure(figsize=(12, 7))

    # Plot Unified Log Data
    plt.scatter(valid_trials, log_drifts, color='#0056b3', s=100, alpha=0.8, edgecolors='black', label='ULS Log Commit')
    plt.axhline(y=mean_log, color='#0056b3', linestyle='--', linewidth=2, label=f'Mean ULS Drift: {mean_log:.3f}s')

    # Plot SQLite WAL Data (Only plot if it actually flushed)
    if mean_wal > 0:
        plt.scatter(valid_trials, wal_drifts, color='#d9534f', s=100, marker='s', alpha=0.8, edgecolors='black', label='SQLite WAL Disk Flush')
        plt.axhline(y=mean_wal, color='#d9534f', linestyle='--', linewidth=2, label=f'Mean WAL Drift: {mean_wal:.3f}s')

    # Formatting
    plt.title('Forensic Artifact Write Delay: ULS vs. Physical Disk Flush (SQLite)', fontsize=15, fontweight='bold', pad=15)
    plt.xlabel('Experimental Trial Number (n=20)', fontsize=12, fontweight='bold')
    plt.ylabel('System Delay / Drift (Seconds)', fontsize=12, fontweight='bold')
    
    plt.xticks(range(1, trials + 1)) 
    plt.grid(True, linestyle=':', alpha=0.7)
    plt.legend(loc='upper right', fontsize=11, framealpha=1)

    plt.savefig(graph_filename, dpi=300, bbox_inches='tight')
    print(f'[+] Success! High-resolution graph saved as {graph_filename}')
else:
    print("[-] No valid data points captured to generate a graph.")
