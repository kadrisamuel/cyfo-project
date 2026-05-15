# Knowledge Base

## Locations of Bluetooth Data

### plists
#### Bluetooth.plist
Includes structured list of keys including DeviceCache or PairedDevices on older macOS versions. Newer (possibly ~Cataline and later) versions have less info, more of a settings/preferences file, but PersistentPorts can display currently connected devices.

Query like:
```
defaults read /Library/Preferences/com.apple.Bluetooth.plist
```
Response for old like:
```
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
and for new like:
```
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

#### MobileBluetooth.devices.plist
In newer macOS, functions similarly to how Bluetooth.plist is for older macOS. Stores per-device pairing data, link keys, device names, MAC addresses, device-specific connection history.
```
sudo defaults read /Library/Bluetooth/Library/Preferences/com.apple.MobileBluetooth.devices.plist
```
Response snippet:
```
{
    "10:94:BB:BF:ED:8C" =     {
        AACPCapabilitiesIntegersLength = 0;
        AACPCapabilitiesLength = 0;
        DefaultName = Keyboard;
        DeviceClass = {length = 4, bytes = 0x40250000};
        DeviceIdProduct = 620;
        DeviceIdVendor = 76;
        DeviceIdVendorSource = 1;
        DeviceIdVersion = 518;
        ...
        LastHIDVersion = {length = 2, bytes = 0x0001};
        LastPNPInformationVersion = {length = 2, bytes = 0x0301};
        LastSeenTime = 1778840374;
        Name = "Kadri's Keyboard";
        ...
        initiateSDPMirroringState = 0;
    };
    ...
```
See full output in [/files/MobileBluetooth.devices.plist.txt](/files/MobileBluetooth.devices.plist.txt)

### /Library sqlite DBs
Request for locations:
``` 
ls -R /Library/Bluetooth
```
Response:
```
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

### Queries to find places that mention bluetooth

Basic query that finds the places we already know of:
```
find /Library -path "/Library/Developer" -prune -o -iname "*bluetooth*" -type f -print
```
Response:
```
/Library/Preferences/com.apple.bluetooth.plist
/Library/Bluetooth/com.apple.MobileBluetooth.ledevices.other.db
/Library/Bluetooth/com.apple.MobileBluetooth.ledevices.other.db-shm
/Library/Bluetooth/Library/Preferences/com.apple.MobileBluetooth.devices.plist
/Library/Bluetooth/com.apple.MobileBluetooth.ledevices.other.db-wal
/Library/Bluetooth/com.apple.MobileBluetooth.ledevices.paired.db-shm
/Library/Bluetooth/com.apple.MobileBluetooth.ledevices.paired.db-wal
/Library/Bluetooth/com.apple.MobileBluetooth.ledevices.paired.db
```

Find all files containing `bluetooth` (case insensitive):
```
find / -path "/Library" -prune -o -path "/System/Volumes/Data/Library/Developer/CoreSimulator/" -prune -o -path "/System" -prune -o -path "/private" -prune -o -iname "*bluetooth*" -type f -print
```
`-type f` looks for files, `-type d` for directories

Chaining pruning paths that contain lots of junk:
```
-path "/PathToPrune" -prune -o
```