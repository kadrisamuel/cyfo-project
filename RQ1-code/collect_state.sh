#!/bin/bash
# collect_state.sh — Step 2: Baseline + state acquisition

# Get prefix from command-line argument, or prompt user if not provided
PREFIX="$1"
if [ -z "$PREFIX" ]; then
  read -p "Enter directory prefix [baseline_clean / after_pair / after_forget]: " PREFIX
  if [ -z "$PREFIX" ]; then
    PREFIX="collect_state_unknown"
  fi
fi

OUT_DIR="./${PREFIX}_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"
mkdir -p "$OUT_DIR/user"
mkdir -p "$OUT_DIR/Bluetooth"

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
sudo cp /Library/Preferences/com.apple.Bluetooth.plist "$OUT_DIR/" || echo "[!] FAILED: plist copy"
sudo cp -R /Library/Bluetooth "$OUT_DIR/" || echo "[!] FAILED: Bluetooth dir copy"
sudo cp /Library/Bluetooth/Library/Preferences/com.apple.MobileBluetooth.devices.plist "$OUT_DIR/" 2>/dev/null
sudo cp /Library/Bluetooth/com.apple.MobileBluetooth.devices.plist "$OUT_DIR/" 2>/dev/null

# Lower-level daemon storage (/private/var/db/blued/)
sudo cp -R /private/var/db/blued "$OUT_DIR/" 2>/dev/null || echo "[!] FAILED: blued copy"

# Legacy system logs (filtering system.log for bluetooth)
if [ -f /private/var/log/system.log ]; then
  grep -i "bluetooth\|blue" /private/var/log/system.log > "$OUT_DIR/legacy_system_bluetooth.log" 2>/dev/null
fi

sudo chown -R $(whoami) "$OUT_DIR"

# User artifacts
cp ~/Library/Preferences/ByHost/com.apple.Bluetooth.* "$OUT_DIR/user/" 
cp ~/Library/Preferences/com.apple.bluetooth.plist* "$OUT_DIR/user/" 
cp ~/Library/Preferences/com.apple.bluetoothuserd.plist* "$OUT_DIR/user/" 

# iCloud account state
defaults read ~/Library/Preferences/MobileMeAccounts.plist > "$OUT_DIR/MobileMeAccounts.plist.txt" 2>/dev/null
cp ~/Library/Preferences/MobileMeAccounts.plist "$OUT_DIR/user/" 2>/dev/null

# SQLite — dump all BT databases
sudo find /Library/Bluetooth -name "*.db" 2>/dev/null | while read -r src_db; do
  db_name=$(basename "$src_db")
  # Copy db + wal + shm
  sudo cp "${src_db}"* "$OUT_DIR/Bluetooth/" 2>/dev/null
  sudo chown $(whoami) "$OUT_DIR/Bluetooth/${db_name}"* 2>/dev/null

  local_db="$OUT_DIR/Bluetooth/$db_name"
  dump_file="$OUT_DIR/${db_name%.db}_dump.sql"
  freelist_file="$OUT_DIR/${db_name%.db}_freelist.txt"

  if [ -f "$local_db" ]; then
    # Checkpoint WAL before dumping
    sqlite3 "$local_db" "PRAGMA wal_checkpoint(FULL);" 2>/dev/null
    sqlite3 "$local_db" .dump > "$dump_file"
    sqlite3 "$local_db" "PRAGMA freelist_count;" > "$freelist_file"
    echo "[+] Dumped: $db_name"
  fi
done

# Unified logs (last 5 min to cover reset window)
log show --last 5m --predicate 'subsystem == "com.apple.bluetooth"' > "$OUT_DIR/bluetooth.log"

sudo chown -R $(whoami) "$OUT_DIR"

# Integrity checksums
find "$OUT_DIR" -type f ! -name "checksums.sha256" -exec shasum -a 256 {} + > "$OUT_DIR/checksums.sha256"

echo "[+] Collection complete: $OUT_DIR"