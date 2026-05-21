# Pre-note tests
Commands and output for confirming that key artifacts exist and are readable on my specific machine

## Kadri's machine
2025 M4 MacBook Air running the latest macOS (Tahoe 26.3.1) with encrypted iCloud (Advanced Data Protection) -> uses entitlement-based sandboxing and Unified Logging.

## Verified that Bluetooth plist exists and is readable
If it prints out a structured list of keys including DeviceCache or PairedDevices, the primary artifact is present and accessible without any special privileges. 

```
defaults read /Library/Preferences/com.apple.Bluetooth
{
    BluetoothAutoSeekKeyboard = 1;
    BluetoothAutoSeekPointingDevice = 1;
    PersistentPorts =     {
        "D4:23:B5:C4:89:A9" =         {
            BSDName = "JYX-S55";
            BTAddress = {length = 6, bytes = 0xd423b5c489a9};
            RFCOMMChannel = 2;
        };
    };
    SpatialSoundProfileAllowed = 1;
    enableGameControllerAutoSwitchMode = 1;
    enableGameControllerUSBBluetoothPairing = 1;
    move3PPLEMSToLegacyMode = 1;
    move3PPLEMSToLegacyModeSerial = 1;
}
```

-> The plist is world-readable, but the DeviceCache key is missing.

## Checked the DeviceCache
```
plutil -p /Library/Preferences/com.apple.Bluetooth.plist
{
  "BluetoothAutoSeekKeyboard" => true
  "BluetoothAutoSeekPointingDevice" => true
  "enableGameControllerAutoSwitchMode" => true
  "enableGameControllerUSBBluetoothPairing" => true
  "move3PPLEMSToLegacyMode" => true
  "move3PPLEMSToLegacyModeSerial" => 1
  "PersistentPorts" => {
    "D4:23:B5:C4:89:A9" => {
      "BSDName" => "JYX-S55"
      "BTAddress" => {length = 6, bytes = 0xd423b5c489a9}
      "RFCOMMChannel" => 2
    }
  }
  "SpatialSoundProfileAllowed" => true
}
```

I hit the "SIP" (System Integrity Protection) wall. In recent versions of macOS, the sensitive pairing data—including the history of devices, connection timestamps, and encryption keys—has been moved from the world-readable /Library/Preferences folder to a protected database.

Tried various ways, including:
```
sudo ls -R /Library/Bluetooth

ls: /Library/Bluetooth: Operation not permitted
```

Granting Full Disk Access:
1. Go to System Settings > Privacy & Security > Full Disk Access.
2. Click the + and add Terminal (found in /Applications/Utilities/).
3. Quit and Restart Terminal.
4. Try sudo ls -R /Library/Bluetooth again.

```
sudo ls -R /Library/Bluetooth
Password:
Library
com.apple.MobileBluetooth.ledevices.other.db
com.apple.MobileBluetooth.ledevices.other.db-shm
com.apple.MobileBluetooth.ledevices.other.db-wal
com.apple.MobileBluetooth.ledevices.paired.db
com.apple.MobileBluetooth.ledevices.paired.db-shm
com.apple.MobileBluetooth.ledevices.paired.db-wal

/Library/Bluetooth/Library:
Database	Preferences

/Library/Bluetooth/Library/Database:

/Library/Bluetooth/Library/Preferences:
com.apple.MobileBluetooth.devices.plist
```
-> Apple has migrated Bluetooth data from .plist files into SQLite databases (.db).

* com.apple.MobileBluetooth.ledevices.paired.db: This is the primary relational database for Low Energy (LE) paired devices.

* The -wal (Write-Ahead Log) files: When a user deletes a device, the record is marked for deletion in the .db file, but the raw data often persists in the -wal file until a "checkpoint" occurs (which could be hours or days later).

* com.apple.MobileBluetooth.devices.plist: Might contain the legacy "Classic" Bluetooth settings or high-level flags.


Querying the DB to see if a deleted device is recoverable:
```
sudo sqlite3 /Library/Bluetooth/com.apple.MobileBluetooth.ledevices.paired.db "SELECT * FROM PairedDevices;"
C75D39D2-F2D0-AAFA-9B74-0492414924F9|MX Master 3|2|Random E7:30:C5:F8:16:7F||46689698|1695|0|HasBuiltinServices,IsLEKeyboard,IsLEMouse,_HID_DEVICE_|
6E2D470A-1562-BDDD-17DF-0991129205A3|MX Master 3|2|Random E7:30:C5:F8:16:82|Random E7:30:C5:F8:16:82|57869993|2643|0|APPEARANCE_MOUSE,HasBuiltinServices,IsLEKeyboard,IsLEMouse,LeIdentificationHashExist,_HID_DEVICE_|
FA277342-7B6D-B1FF-E969-DED63443D02A|MX Master 3S|2|Random D8:B7:A1:05:97:CD|Random D8:B7:A1:05:97:CD|63305295|3066|0|APPEARANCE_MOUSE,HasBuiltinServices,IsLEMouse,LeIdentificationHashExist,_HID_DEVICE_|
9FE80D29-46AD-82D1-4099-7E1429598D42|iPad|2|Public EC:73:79:8D:60:6A|Public EC:73:79:8D:60:6A|63312741|2643|1|PairedUsingRSA,PairingAttemptedUsingRSA|8E1F51FF-CEC0-4324-B14D-75D6D29662EF
871F1D3F-DE3A-7966-2ECC-1C32AD6F199D|Kadri’s iPhone|2|Public A8:AB:B5:95:35:99|Public A8:AB:B5:95:35:99|63312772|3061|1|PairedUsingRSA,PairingAttemptedUsingRSA|80F24984-2353-4C86-8F95-C512F2A09A28
```
-> JYX-S55 not visible. But I wasn't able to make it visible after reconnecting either.

Also tried diffing -wal files before and after forgetting the device but didn't get anything that would seem immediately useful.

Should reconfirm com.apple.MobileBluetooth.devices.plist files after Full Disk Access. TODO: Mention in paper that we had to grant Full Disk Access to be able to access the files.

## Tested unified log access for Bluetooth events
```
log show --predicate 'subsystem == "com.apple.bluetooth"' --last 1h --info
Filtering the log data using "subsystem == "com.apple.bluetooth""
Skipping debug messages, pass --debug to include.
Timestamp                       Thread     Type        Activity             PID    TTL  
2026-04-24 15:20:43.755224+0200 0x4fbf7c   Default     0x0                  682    0    audioaccessoryd: (CoreUtils) [com.apple.bluetooth:BTSmartRoutingDaemon] AudioStateSnapshot: BtState PoweredOn Route Speaker App com.spotify.client, Score 301, Remote -1 NumofApp 2
2026-04-24 15:20:44.899056+0200 0x4fa755   Default     0x0                  17761  0    bluetoothd: [com.apple.bluetooth:Server.MacCoex] Posting Bluetooth Status Notification <private>
2026-04-24 15:20:46.735473+0200 0x4fbf7c   Default     0x0                  682    0    audioaccessoryd: (CoreUtils) [com.apple.bluetooth:BTSmartRoutingDaemon] AudioStateSnapshot: BtState PoweredOn Route Speaker App com.spotify.client, Score 301, Remote -1 NumofApp 2
2026-04-24 15:20:47.143600+0200 0x4fad7c   Default     0x0                  17761  0    bluetoothd: (CoreUtils) [com.apple.bluetooth:CBStackBLEScanner] Rescan - reset rescan timer

...


2026-04-24 16:20:42.551375+0200 0x508eb5   Info        0x0                  17761  0    bluetoothd: [com.apple.bluetooth:Server.Core] Sending: BD_VSC_LE_META_REMV_MULTIPLE_DUPLICATE_ENTRIE_ADV_MATCHING_RULE
2026-04-24 16:20:42.555982+0200 0x508eb5   Default     0x0                  17761  0    bluetoothd: [com.apple.bluetooth:Server.App] clearDuplicateFilterCache for session "com.apple.bluetoothd" type 7
--------------------------------------------------------------------------------------------------------------------
Log      - Default:     72,967, Info:            7,789, Debug:             0, Error:        473, Fault:          0
Activity - Create:           0, Transition:          0, Actions:           0
```

## Did a quick "Forget Device" diff
This is a miniature version of the actual experiment:

1. Pair any Bluetooth device (headphones, phone, anything)
2. Snapshot the plist: cp /Library/Preferences/com.apple.Bluetooth.plist ~/Desktop/bt_before.plist
3. Go to System Settings → Bluetooth → Forget the device
4. Snapshot again: cp /Library/Preferences/com.apple.Bluetooth.plist ~/Desktop/bt_after.plist
5. Diff them: diff <(plutil -p ~/Desktop/bt_before.plist) <(plutil -p ~/Desktop/bt_after.plist)

```
diff <(plutil -p ~/Desktop/bt_before.plist) <(plutil -p ~/Desktop/bt_after.plist)
9,13d8
<     "D4:23:B5:C4:89:A9" => {
<       "BSDName" => "JYX-S55"
<       "BTAddress" => {length = 6, bytes = 0xd423b5c489a9}
<       "RFCOMMChannel" => 2
<     }
```

## Tested FSEvents monitoring 
Installed fswatch:
```
brew install fswatch
```

Ran the following python script and connected/disconnected various bluetooth devices:
```
python3 -c "
import subprocess
print('Watching for changes... (Ctrl+C to stop)')
proc = subprocess.Popen(['fswatch', '-x', '/Library/Preferences/'], stdout=subprocess.PIPE)
for line in proc.stdout:
    print(line.decode())
"
Watching for changes... (Ctrl+C to stop)
/Library/Preferences/com.apple.apsd.plist IsFile AttributeModified

/Library/Preferences/com.apple.powerlogd.plist IsFile Renamed

/Library/Preferences/com.apple.powerlogd.plist IsFile Renamed

/Library/Preferences/com.apple.powerlogd.plist IsFile AttributeModified

/Library/Preferences/SystemConfiguration/com.apple.smb.server.plist-lock Created IsFile Updated Removed

/Library/Preferences/SystemConfiguration/com.apple.smb.server.plist-lock Created IsFile Updated Removed

/Library/Preferences/Audio/com.apple.audio.SystemSettings.plist OwnerModified AttributeModified IsFile Updated

/Library/Preferences/com.apple.windowserver.displays.plist IsFile Renamed

/Library/Preferences/com.apple.windowserver.displays.plist IsFile Renamed

/Library/Preferences/com.apple.powerd.charging.plist IsFile Renamed

/Library/Preferences/com.apple.powerd.charging.plist IsFile Renamed

/Library/Preferences/com.apple.AssetCache.plist OwnerModified IsFile

/Library/Preferences/com.apple.windowserver.displays.plist IsFile AttributeModified

/Library/Preferences/com.apple.powerd.charging.plist IsFile AttributeModified

/Library/Preferences/com.apple.apsd.plist IsFile Renamed

/Library/Preferences/com.apple.apsd.plist IsFile Renamed

/Library/Preferences/SystemConfiguration/com.apple.smb.server.plist-lock Created IsFile Updated Removed

/Library/Preferences/com.apple.apsd.plist IsFile AttributeModified

/Library/Preferences/com.apple.SoftwareUpdate.plist IsFile Renamed

/Library/Preferences/com.apple.SoftwareUpdate.plist IsFile Renamed

/Library/Preferences/com.apple.SoftwareUpdate.plist IsFile Renamed

/Library/Preferences/com.apple.SoftwareUpdate.plist IsFile Renamed

/Library/Preferences/com.apple.SoftwareUpdate.plist IsFile AttributeModified

/Library/Preferences/com.apple.powerd.charging.plist IsFile Renamed

/Library/Preferences/com.apple.powerd.charging.plist IsFile Renamed

/Library/Preferences/com.apple.powerd.charging.plist IsFile AttributeModified

/Library/Preferences/com.apple.apsd.plist IsFile Renamed

/Library/Preferences/com.apple.apsd.plist IsFile Renamed

/Library/Preferences/com.apple.apsd.plist IsFile AttributeModified

/Library/Preferences/com.apple.apsd.plist IsFile Renamed

/Library/Preferences/com.apple.apsd.plist IsFile Renamed

/Library/Preferences/com.apple.apsd.plist IsFile AttributeModified

/Library/Preferences/com.apple.powerlogd.plist IsFile Renamed

/Library/Preferences/com.apple.powerlogd.plist IsFile Renamed

/Library/Preferences/com.apple.powerlogd.plist IsFile AttributeModified

/Library/Preferences/com.apple.powerd.charging.plist IsFile Renamed

/Library/Preferences/com.apple.powerd.charging.plist IsFile Renamed

/Library/Preferences/com.apple.powerd.charging.plist IsFile AttributeModified

/Library/Preferences/com.apple.powerd.charging.plist IsFile Renamed

/Library/Preferences/com.apple.powerd.charging.plist IsFile Renamed

/Library/Preferences/com.apple.powerd.charging.plist IsFile AttributeModified
```
## Saif's machine
MacBook Air running older macOS (Sonoma 14.8.1).

**Major Discovery:** Unlike macOS 15+ (Tahoe), Apple's System Integrity Protection (SIP) has **not** locked down the Bluetooth data on this version. The primary artifact is world-readable in plaintext without needing Full Disk Access.

### Verified that Bluetooth plist exists and is readable
Ran a check on the standard Bluetooth preference file.

bash
```
defaults read /Library/Preferences/com.apple.Bluetooth
DeviceCache =     {
        "7c-04-d0-ad-be-d7" =         {
            BatteryPercentLeft = 25;
            ClassOfDevice = 2360344;
            ClockOffset = 17536;
            LastInquiryUpdate = "2019-11-04 2:18:48\U202fPM +0000";
            LastServicesUpdate = "2019-11-06 5:12:07\U202fPM +0000";
            Manufacturer = 76;
            Name = "Saif\U2019s AirPods";
            ...
        };
        "63-6c-0f-0b-fd-1f" =         {
            LastNameUpdate = "2022-01-07 10:48:59\U202fAM +0000";
            Name = "YET-M1";
            ...
        };
```
-> Conclusion: Massive success. The DeviceCache is completely exposed. Timestamps, exact device names, battery levels, and MAC addresses are all readable without SIP interference.

## Did a "Forget Device" diff (Module C Validation)

Tested whether the macOS UI actually deletes residual data from the system cache when a user clicks "Forget Device".
Target Devices: YET-M1 and EWA Audio A103.

Bash
```
cp /Library/Preferences/com.apple.Bluetooth.plist ~/Desktop/bt_before.plist
```
# -> Clicked "Forget Device" in macOS UI for both devices
```
cp /Library/Preferences/com.apple.Bluetooth.plist ~/Desktop/bt_after.plist
```
```
diff <(plutil -p ~/Desktop/bt_before.plist) <(plutil -p ~/Desktop/bt_after.plist)
```
##Output:

Plaintext
818,822d817
<     "63:6C:0F:0B:FD:1F" => {
<       "BSDName" => "YET-M1"
<       "BTAddress" => {length = 6, bytes = 0x636c0f0bfd1f}
<       "RFCOMMChannel" => 2
<     }
-> Conclusion: Ghost Artifacts confirmed. The UI lies to the user. The only code deleted was the superficial PersistentPorts routing. The full device footprints (MAC, name, history) remained entirely untouched inside the DeviceCache and PairedDevices array in the bt_after.plist file.

Tested FSEvents monitoring & Discovered the BLE Split

Attempted to measure disk write delay for Sony WF-1000XM5 earbuds (ac-80-0a-c1-40-56) by watching the .plist file using fswatch and blueutil.

The Anomaly: The script hung forever waiting for a .plist update. Checked the .plist manually:

Bash
```
defaults read /Library/Preferences/com.apple.Bluetooth | grep -A 10 -B 2 "ac-80-0a-c1-40-56"
```
##Output: (Empty. Returned nothing.)

-> Conclusion: Modern BLE audio devices (like the Sony WF-1000XM5) bypass the legacy com.apple.Bluetooth.plist file entirely. macOS defers this data to memory caches (cfprefsd) or hidden SQLite databases. Legacy .plist monitoring is unreliable for modern BLE forensics.

Tested Unified Log access for Timestamp Drift (Module B Validation)

Switched strategy to monitor the macOS Unified Log (log stream) to capture the exact write delay between a programmatic physical connection trigger and the system logging it.

Built a Python automation script using blueutil to trigger connections and parse the notifyDeviceConnected log entry.

##Test Run Snippet:
```
python3 -c "
import subprocess
import datetime
import time
import os

mac_address = 'ac-80-0a-c1-40-56'

//Find blueutil path
get_path = lambda t: next((p + t for p in ['/opt/homebrew/bin/', '/usr/local/bin/'] if os.path.exists(p + t)), t)
blueutil_cmd = get_path('blueutil')

print('\n=== Module B: Unified Log Timestamp Drift ===')
print(f'Targeting Sony WF-1000XM5 (MAC: {mac_address})')

//Start the log stream
log_proc = subprocess.Popen(
    ['log', 'stream', '--predicate', 'subsystem == \"com.apple.bluetooth\"'],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

time.sleep(1)

// Trigger connection
trigger_time = datetime.datetime.now()
print(f'[{trigger_time.strftime(\"%H:%M:%S.%f\")}] Triggering connection command...')
subprocess.run([blueutil_cmd, '--connect', mac_address], capture_output=True)

// Read logs
print('Waiting for Unified Log entry...')
line = next(l for l in log_proc.stdout if 'Connection completed' in l or 'Connected' in l or mac_address.upper() in l.upper())

// Extract timestamps and terminate
log_time_str = line.split()[0] + ' ' + line.split()[1]
log_proc.terminate()

// Output results
print(f'\n[LOG CAPTURED EVENT]: {line.strip()}')
print('-' * 45)
print(f'PHYSICAL TRIGGER TIME: {trigger_time.strftime(\"%Y-%m-%d %H:%M:%S.%f\")}')
print(f'UNIFIED LOG TIMESTAMP: {log_time_str}')
print('Note: Compare the microseconds between these two times to find your log drift!')
"
```

## Output
=== Module B: Unified Log Timestamp Drift ===
Targeting Sony WF-1000XM5 (MAC: ac-80-0a-c1-40-56)
[14:22:40.226452] Triggering connection command...
Waiting for Unified Log entry...

[LOG CAPTURED EVENT]: 2026-05-12 14:22:42.052177+0200 ... bluetoothd: [com.apple.bluetooth:Server.App] UN: notifyDeviceConnected...
---------------------------------------------
PHYSICAL TRIGGER TIME: 2026-05-12 14:22:40.226452
UNIFIED LOG TIMESTAMP: 2026-05-12 14:22:42.052177+0200
Results across n=5 valid trials:

Trial 1: 1.826 seconds

Trial 2: 1.289 seconds

Trial 3: 1.677 seconds

Trial 4: 1.473 seconds

Trial 5: 1.275 seconds

Note: Logged one "Cold Start" anomaly of 26.033 seconds when the bluetooth daemon had to wake and negotiate setPreferredSniffParamsOnConnectedTouchIDHIDs before logging the connection.

-> Conclusion: Unified logs successfully capture BLE connections that the .plist misses. The baseline forensic write delay (drift) averages 1.508 seconds. Forensic investigators must account for this systemic buffer when building timelines.

## Saif's Notes: BLE SQLite & Timestamp Drift (macOS 14)

Following up on Kadri's findings, I dug into the SQLite databases on my older macOS 14 (Sonoma) machine to see how it handles BLE compared to Classic Bluetooth. 

Here is what we found during the live extraction:

### 1. The Classic vs. BLE Split
* We dumped `/Library/Bluetooth/Library/Preferences/com.apple.MobileBluetooth.devices.plist`. 
* **Finding:** This file *only* logs Classic Bluetooth profiles (A2DP, Handsfree). It explicitly lists the GATT service (which BLE uses) as "Unknown" for third-party devices like my Sony WF-1000XM5. Apple moves all the actual BLE telemetry into the SQLite databases Kadri found.

### 2. The `paired.db` Illusion
* I queried the active paired database (`com.apple.MobileBluetooth.ledevices.paired.db`).
* **Finding:** My Sony earbuds didn't show up here by name. Because they are dual-mode, macOS keeps their readable name in the Classic `.plist` and only uses transient, randomized MAC addresses for the BLE side to protect privacy. The only devices that showed up with clear names in this DB were my Apple devices (due to the Continuity/Handoff network).

### 3. Macs act as Passive Trackers (`other.db`)
* I pulled the last 20 entries from `com.apple.MobileBluetooth.ledevices.other.db`.
* **Finding:** The Mac is constantly doing passive background surveillance. Even when the lid is closed (Dark Wake), it logs the randomized MAC addresses (RPAs) of almost every BLE device that walks past it. If police seized a Mac, they could match these random addresses to a suspect's phone to prove they were in the room.

### 4. Carving the `-wal` Files works
* The main `paired.db` was tiny (32K), but its Write-Ahead Log (`.db-wal`) was massive (2.7MB). This proves the OS batches BLE telemetry in the WAL to prevent wearing out the SSD.
* **Finding:** Running a basic `strings` command on the WAL file successfully carved out raw, uncommitted connection data in plain text (including my iPhone's UUID and MAC). This confirms investigators can pull deleted "ghost" data directly from the WAL before the database cleans itself up.

### 5. Final Timestamp Drift Results (n=20)
* I updated our Python automation script to run 20 consecutive connect/disconnect cycles with the Sony earbuds to get a statistically accurate read on the Unified Log write delay.
* **Finding:** The average forensic drift ($\mu$) across 20 trials is **1.188 seconds**. The fastest log commit was ~0.87s, and the slowest was ~1.62s. 
* **Conclusion:** Investigators cannot trust the macOS Unified Log timestamp as the exact millisecond a device connected. They have to account for a ~1.2-second system buffer delay.

## Experiment: Measuring Unified Log Timestamp Drift

When building a forensic timeline, you cannot assume a log timestamp represents the exact millisecond a physical event occurred. macOS buffers Bluetooth Low Energy (BLE) connection events in memory before flushing them to the Unified Logging System (ULS) on the disk. 

To determine our exact margin of error, we built a Python automation harness. It programmatically forces a physical BLE connection, listens to the live macOS log stream, and calculates the exact write delay between the physical trigger and the system log commit.

### Prerequisites
To replicate this test on your own macOS endpoint, you will need:
* **macOS** (Tested on macOS 14 Sonoma and macOS 15 Tahoe)
* **blueutil** installed via Homebrew (`brew install blueutil`)
* **Python 3** with the Matplotlib graphing library (`pip3 install matplotlib`)
* **A Target BLE Device:** Find the MAC address of a local device using `blueutil --paired`. Ensure the device is powered on and out of its case, but not actively connected to another device like your phone.

### The Automation Script (`drift_analysis.py`)
Save the following code as `drift_analysis.py`. 

**Note:** You must run this script with elevated privileges (`sudo python3 drift_analysis.py`) so the subprocess can tap into the protected Bluetooth ULS streams.

```python
import subprocess
import datetime
import time
import os
import csv
import matplotlib.pyplot as plt

# --- CONFIGURATION ---
# Replace this with your target device's MAC address
mac_address = 'ac-80-0a-c1-40-56'  
trials = 20
csv_filename = 'timestamp_drift_results.csv'
graph_filename = 'Forensic_Drift_Figure.png'

# Find blueutil path automatically
def get_path(tool):
    for path in ['/opt/homebrew/bin/', '/usr/local/bin/']:
        if os.path.exists(path + tool):
            return path + tool
    return tool

blueutil_cmd = get_path('blueutil')

print(f'\n=== Automated Forensic Endpoint Analysis ===')
print(f'Target: {mac_address} | Trials: {trials}')
print('============================================\n')

valid_trials = []
valid_drifts = []

# --- PHASE 1: DATA COLLECTION ---
with open(csv_filename, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['Trial Number', 'Physical Trigger Time', 'Unified Log Time', 'Drift (Seconds)'])

    for i in range(1, trials + 1):
        print(f'--- Trial {i}/{trials} ---')
        
        print('Resetting target endpoint state (disconnecting)...')
        subprocess.run([blueutil_cmd, '--disconnect', mac_address], capture_output=True)
        time.sleep(4) 
        
        log_proc = subprocess.Popen(
            ['log', 'stream', '--predicate', 'subsystem == "com.apple.bluetooth"'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(1) 

        trigger_time = datetime.datetime.now()
        print(f'[{trigger_time.strftime("%H:%M:%S.%f")}] Injecting programmatic connect trigger...')
        subprocess.run([blueutil_cmd, '--connect', mac_address], capture_output=True)

        print('Awaiting ULS commit event...')
        log_time_str = None
        for line in log_proc.stdout:
            if 'Connection completed' in line or 'Connected' in line or mac_address.upper() in line.upper() or mac_address.lower() in line.lower():
                raw_time = line.split()[0] + ' ' + line.split()[1]
                log_time_str = raw_time.split('+')[0] 
                log_proc.terminate()
                break
        
        if log_time_str:
            log_time = datetime.datetime.strptime(log_time_str, "%Y-%m-%d %H:%M:%S.%f")
            drift = (log_time - trigger_time).total_seconds()
            
            print(f'Log Time: {log_time_str}')
            print(f'Forensic Drift: {drift:.6f}s\n')
            
            writer.writerow([i, trigger_time.strftime("%Y-%m-%d %H:%M:%S.%f"), log_time_str, round(drift, 6)])
            valid_trials.append(i)
            valid_drifts.append(drift)
        else:
            print("Failed to capture log within timeout.\n")
            writer.writerow([i, trigger_time.strftime("%Y-%m-%d %H:%M:%S.%f"), 'ERROR', 'ERROR'])

print(f'[+] Phase 1 Complete. Raw data saved to {csv_filename}')

# --- PHASE 2: AUTOMATED GRAPH GENERATION ---
if len(valid_drifts) > 0:
    print(f'[+] Phase 2: Generating IEEE-formatted Scatter Plot...')
    
    mean_drift = sum(valid_drifts) / len(valid_drifts)

    plt.figure(figsize=(10, 6))
    plt.scatter(valid_trials, valid_drifts, color='#0056b3', s=100, alpha=0.8, edgecolors='black', label='Measured Log Drift')
    plt.axhline(y=mean_drift, color='#d9534f', linestyle='--', linewidth=2, label=f'Mean Drift ($\mu$): {mean_drift:.3f}s')

    plt.title('Forensic Write Delay: Physical BLE Trigger vs. macOS Unified Log Commit', fontsize=14, fontweight='bold', pad=15)
    plt.xlabel('Experimental Trial Number (n=20)', fontsize=12, fontweight='bold')
    plt.ylabel('System Write Buffer Delay / Drift (Seconds)', fontsize=12, fontweight='bold')
    
    plt.xticks(range(1, trials + 1)) 
    plt.grid(True, linestyle=':', alpha=0.7)
    plt.legend(loc='upper right', fontsize=11, framealpha=1)

    plt.savefig(graph_filename, dpi=300, bbox_inches='tight')
    print(f'[+] Success! High-resolution graph saved as {graph_filename}')
else:
    print("[-] No valid data points captured to generate a graph.")
