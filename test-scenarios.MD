# Test Scenarios

## RQ1 — Persistence after “Forget Device”

Run multiple scenarios:
* Forget immediately after pairing
* Forget after multiple connections
* Forget after reboot
* Forget and reboot
* Forget while device is disconnected

Measure for each artifact, does the device entry:
* disappear completely?
* remain partially (e.g., MAC address)?
* remain in another file but not UI?

## How to run?
Use correct EXP# and MAC address for each experiment

**`collect_state.sh` usage**: `./collect_state.sh <dir>`

**`log_results.sh` usage**: `./log_results.sh <dir> <experiment_id> <phase> <device_type> <mac1> ...`

## Important arguments

* `<dir>` — directory to store the collected data, corresponds to experiment phase (baseline_clean, after_pair, after_forget) and may have a timestamp suffix added by `collect_state.sh`.
* `<experiment_id>` — identifier for the experiment (e.g., EXP1)
* `<phase>` — phase of the experiment (baseline_clean, after_pair, after_forget)
* `<device_type>` — type of device (mouse, keyboard, headphones, speaker, etc.)
* `<mac1> ...` — one or more MAC addresses of the device


### Step 1: Clean baseline
```
./reset_bt.sh
./collect_state.sh baseline_clean
./log_results.sh baseline_clean_timestamp EXP1 baseline mouse F8:4D:89:4C:79:D7
```

### Step 2: Pair and connect device manually

### Step 3: Collect data
```
./collect_state.sh after_pair
./log_results.sh after_pair_timestamp EXP1 paired mouse F8:4D:89:4C:79:D7
```

### Step 4: Forget device

### Step 5: Collect and analyze data
```
./collect_state.sh after_forget

# run carving first
./carve_ble.sh after_forget/Library/Bluetooth/com.apple.MobileBluetooth.ledevices.paired.db

./log_results.sh after_forget_timestamp EXP1 after_forget mouse F8:4D:89:4C:79:D7
```

## Variables to control

* macOS version
* Hardware:
    * Apple Silicon vs Intel
* Device type:
    * Apple (AirPods, Magic Mouse)
    * BLE (fitness tracker, beacon)
    * Classic BT (keyboard, speaker)
* iCloud state:
    * ON vs OFF
* Connection state:
    * Paired (or has been paired in the past) 
    * New (Never paired)
* Bluetooth type:
    * BLE
    * Classic Bluetooth

## Variables to measure

* Artifact presence (before vs after “Forget Device”)
* Timestamp values across sources
* Residual entries (deleted vs partially removed)
* Cross-device reappearance (iCloud sync)

## Workflow

1. Clean system (TODO: check order)
* Reset BT subsystem
* Dump all baseline artifacts
* Record base state
2. Test execution
* Start relevant scripts for logging
* Pair, connect, and forget device
3. Forensic capture
Record
* plist files
* BLE database
* unified logs
* ...
Analyze
* Diff all recorded files
* Carve SQLite freelist

## Artifact targets

* /Library/Preferences/com.apple.Bluetooth.plist
* /Library/Bluetooth/com.apple.MobileBluetooth.devices.plist
* /Library/Bluetooth/com.apple.MobileBluetooth.ledevices.paired.db
* /private/var/db/blued/
→ Lower-level daemon storage
* /private/var/log/ (legacy logs on older macOS)
* Unified logs (primary for timing)

User-level:
* ~/Library/Preferences/ByHost/com.apple.Bluetooth.*.plist
iCloud-related:
* ~/Library/Preferences/MobileMeAccounts.plist

