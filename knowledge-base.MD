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

### /Library SQLite DBs
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
Based on the naming, it seems that SQLIte DBs contain BLE device data.

**Extensions explained:**

.db | The main database file

.db-shm | Shared memory file — just a memory index

.db-wal | Write-Ahead Log — temporarily holds changes before they're committed to the main .db file

#### Paired BLE devices
`MobileBluetooth.ledevices.paired.db` tracks BLE devices that have been paired.

Request to get schema for `MobileBluetooth.ledevices.paired.db`:
```
sudo sqlite3 /Library/Bluetooth/com.apple.MobileBluetooth.ledevices.paired.db ".schema"      
```
Response:
```               
CREATE TABLE _SqliteDatabaseProperties(key TEXT, value TEXT, UNIQUE(key));
CREATE TABLE PairedDevices(Uuid TEXT, Name TEXT, NameOrigin INT, Address TEXT, ResolvedAddress TEXT, LastSeenTime INT, LastConnectionTime INT, GATTServiceChangeConfig INT, Tags TEXT, iCloudIdentifier TEXT);
CREATE INDEX UuidIndex ON PairedDevices(Uuid);
CREATE TABLE CustomProperties (Uuid TEXT, JSON TEXT, UNIQUE(Uuid));
CREATE INDEX CustomPropertiesIndex ON CustomProperties (Uuid);
```

DB query and response:
```
sudo sqlite3 /Library/Bluetooth/com.apple.MobileBluetooth.ledevices.paired.db "SELECT * FROM PairedDevices;"
Password:
C75D39D2-F2D0-AAFA-9B74-0492414924F9|MX Master 3|2|Random E7:30:C5:F8:16:7F||46689698|1695|0|HasBuiltinServices,IsLEKeyboard,IsLEMouse,_HID_DEVICE_|
6E2D470A-1562-BDDD-17DF-0991129205A3|MX Master 3|2|Random E7:30:C5:F8:16:82|Random E7:30:C5:F8:16:82|57869993|2643|0|APPEARANCE_MOUSE,HasBuiltinServices,IsLEKeyboard,IsLEMouse,LeIdentificationHashExist,_HID_DEVICE_|
9FE80D29-46AD-82D1-4099-7E1429598D42|iPad|2|Public EC:73:79:8D:60:6A|Public EC:73:79:8D:60:6A|63972174|2643|1|PairedUsingRSA,PairingAttemptedUsingRSA|8E1F51FF-CEC0-4324-B14D-75D6D29662EF
CE1A473D-EC38-5B5F-0D35-8347D4E06FAD|MX Anywhere 2S|2|Random FF:1C:A9:E3:78:B5|Random FF:1C:A9:E3:78:B5|64222109|2844|0|APPEARANCE_MOUSE,HasBuiltinServices,IsLEKeyboard,IsLEMouse,_HID_DEVICE_|
FA277342-7B6D-B1FF-E969-DED63443D02A|MX Master 3S|2|Random D8:B7:A1:05:97:CD|Random D8:B7:A1:05:97:CD|64377236|2610|0|APPEARANCE_MOUSE,HasBuiltinServices,IsLEMouse,LeIdentificationHashExist,_HID_DEVICE_|
871F1D3F-DE3A-7966-2ECC-1C32AD6F199D|Kadri’s iPhone|2|Public A8:AB:B5:95:35:99|Public A8:AB:B5:95:35:99|64434051|2891|1|PairedUsingRSA,PairingAttemptedUsingRSA|80F24984-2353-4C86-8F95-C512F2A09A28
```

The output for reading .db-wal file using:
```
sudo strings /Library/Bluetooth/com.apple.MobileBluetooth.ledevices.paired.db-wal > ledevices.paired.db-wal.txt
```
can be found [here](/files/ledevices.paired.db-wal.txt).

#### Other BLE devices
`MobileBluetooth.ledevices.other.db` tracks BLE devices that have been seen/discovered but not paired (nearby sensors, beacons, fitness trackers, or any BLE device detected in the vicinity).

Request to get schema for `MobileBluetooth.ledevices.other.db`;
```
sudo sqlite3 /Library/Bluetooth/com.apple.MobileBluetooth.ledevices.other.db ".schema" 
```
Response:
```         
CREATE TABLE _SqliteDatabaseProperties(key TEXT, value TEXT, UNIQUE(key));
CREATE TABLE OtherDevices(Uuid TEXT, Name TEXT, NameOrigin INT, Address TEXT, ResolvedAddress TEXT, LastSeenTime INT, LastConnectionTime INT, GATTServiceChangeConfig INT, Tags TEXT, iCloudIdentifier TEXT);
CREATE INDEX UuidIndex ON OtherDevices(Uuid);
CREATE TABLE CustomProperties (Uuid TEXT, JSON TEXT, UNIQUE(Uuid));
CREATE INDEX CustomPropertiesIndex ON CustomProperties (Uuid);
```

### Queries to find places that mention Bluetooth in the file system

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