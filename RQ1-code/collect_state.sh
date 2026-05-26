#!/bin/bash
# collect_state.sh — Step 2: Baseline + state acquisition

OUT_DIR="./pre_test_baseline_clean_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"

echo "[*] Collecting baseline system state into $OUT_DIR"

# Guard: warn if daemon isn't running
pgrep bluetoothd > /dev/null || echo "[!] WARNING: bluetoothd not running at collection time"

# Let daemon settle after reset
sleep 3

# Timestamp
date -u +"%Y-%m-%d %H:%M:%S UTC" > "$OUT_DIR/timestamp.txt"

# System info
system_profiler SPBluetoothDataType > "$OUT_DIR/system_bluetooth.txt"

# Core artifacts
sudo cp /Library/Preferences/com.apple.Bluetooth.plist "$OUT_DIR/" 2>/dev/null
sudo cp -R /Library/Bluetooth "$OUT_DIR/" 2>/dev/null

# User artifacts
cp ~/Library/Preferences/ByHost/com.apple.Bluetooth.* "$OUT_DIR/" 2>/dev/null

# iCloud account state
defaults read ~/Library/Preferences/MobileMeAccounts.plist > "$OUT_DIR/MobileMeAccounts.plist.txt" 2>/dev/null

# SQLite dump — include WAL/SHM for consistency
DB="$OUT_DIR/Bluetooth/com.apple.MobileBluetooth.ledevices.paired.db"
sudo cp /Library/Bluetooth/com.apple.MobileBluetooth.ledevices.paired.db* "$OUT_DIR/Bluetooth/" 2>/dev/null

if [ -f "$DB" ]; then
  sqlite3 "$DB" .dump > "$OUT_DIR/ble_db_dump.sql"
  sqlite3 "$DB" "PRAGMA freelist_count;" > "$OUT_DIR/freelist_count.txt"
else
  echo "[!] WARNING: BLE database not found"
fi

# Unified logs (last 5 min to cover reset window)
log show --last 5m --predicate 'subsystem == "com.apple.bluetooth"' > "$OUT_DIR/bluetooth.log"

# Integrity checksums
find "$OUT_DIR" -type f ! -name "checksums.sha256" -exec shasum -a 256 {} + > "$OUT_DIR/checksums.sha256"

if [ ! -f "$OUT_DIR/ble_db_dump.sql" ]; then
  echo "[!] WARNING: BLE database dump failed"
else
  echo "[+] Collection complete: $OUT_DIR"
fi