# Pre-note tests
Commands and output for confirming that key artifacts exist and are readable on my specific machine

## Kadri's machine
2025 M4 MacBook Air running the latest macOS (Tahoe 26.3.1) with encrypted iCloud (Advanced Data Protection) -> uses entitlement-based sandboxing and Unified Logging.

## Verified that Bluetooth plist exists and is readable
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

I hit the "SIP" (System Integrity Protection) wall. In recent versions of macOS, the sensitive pairing data—including the history of devices, connection timestamps, and encryption keys—has been moved from the world-readable /Library/Preferences folder to a protected database in /var/db/bluetooth/.

To get that data, you have to escalate your privileges and target the specific "com.apple.Bluetooth.plist" located in that protected directory.

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