#!/bin/bash
# reset_bt.sh
# Step 1
# Reset / clean Bluetooth environment

echo "[*] Resetting Bluetooth subsystem..."

# Timestamped backup dir
BACKUP_DIR="./backup_pre_reset_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Kill the Bluetooth daemon
BT_PID=$(pgrep bluetoothd)
if [ -z "$BT_PID" ]; then
  echo "[!] bluetoothd not running — continuing anyway"
else
  sudo kill -9 "$BT_PID"
  # Make sure it is dead
  for i in {1..5}; do
    pgrep bluetoothd > /dev/null || break
    sleep 1
  done
  pgrep bluetoothd > /dev/null && echo "[!] WARNING: bluetoothd still alive" && exit 1
fi

# Backup before deletion (just in case)
sudo cp -R /Library/Bluetooth "$BACKUP_DIR/" 2>/dev/null
sudo cp /Library/Preferences/com.apple.Bluetooth.plist "$BACKUP_DIR/" 2>/dev/null
cp ~/Library/Preferences/ByHost/com.apple.Bluetooth.* "$BACKUP_DIR/" 2>/dev/null

# Remove Bluetooth state
sudo rm -rf /Library/Bluetooth/*
sudo rm -f /Library/Preferences/com.apple.Bluetooth.plist

# User-level artifacts
rm -f ~/Library/Preferences/ByHost/com.apple.Bluetooth.*

# Restart daemon
sudo launchctl start com.apple.bluetoothd

echo "[+] Bluetooth reset complete. Backup at: $BACKUP_DIR"