# Test Scenarios

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