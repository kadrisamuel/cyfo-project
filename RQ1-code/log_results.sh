#!/bin/bash
# log_results.sh

OUTDIR=$1
EXPERIMENT_ID=$2
PHASE=$3
DEVICE_TYPE=$4
shift 4
MACS=("$@")

CSV="results.csv"

if [ -z "$OUTDIR" ] || [ -z "$EXPERIMENT_ID" ] || [ -z "$PHASE" ]; then
  echo "Usage: ./log_results.sh <dir> <experiment_id> <phase> <device_type> <mac1> ..."
  exit 1
fi

if [ ! -d "$OUTDIR" ]; then
  echo "[!] Directory not found: $OUTDIR"
  exit 1
fi

if [ ${#MACS[@]} -eq 0 ]; then
  echo "[!] No MAC addresses provided"
  exit 1
fi

# --- Environment Capture ---
MACOS_VERSION=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
ARCH=$(uname -m 2>/dev/null || echo "unknown")
HW_MODEL=$(system_profiler SPHardwareDataType 2>/dev/null \
  | awk -F': ' '/Model Identifier/{print $2; exit}')
HW_MODEL="${HW_MODEL:-unknown}"

echo "[*] Environment: macOS=$MACOS_VERSION arch=$ARCH model=$HW_MODEL"

# Create CSV header if not exists
if [ ! -f "$CSV" ]; then
  echo "experiment_id,phase,timestamp,mac,device_type,macos_version,arch,hw_model,found_plist,found_byhost,found_ble_db,found_strings,freelist_count,recovered_in_sqlite,carved_records_count,notes,found_mac_filesystem_count,found_mac_after_forget" > "$CSV"
fi

TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S")

FREELIST=0
for f in "$OUTDIR"/*_freelist.txt; do
  [ -f "$f" ] || continue
  val=$(cat "$f" 2>/dev/null)
  FREELIST=$((FREELIST + val))
done

# Convert system plist once for all MACs
PLIST="$OUTDIR/com.apple.Bluetooth.plist"
PLIST_XML="/tmp/bt_plist_readable.xml"
if [ -f "$PLIST" ]; then
  plutil -convert xml1 -o "$PLIST_XML" "$PLIST" 2>/dev/null
  echo "[*] System plist found and converted"
else
  echo "[!] System plist not found in $OUTDIR"
fi

# Convert devices plist once for all MACs
DEVICES_PLIST="$OUTDIR/com.apple.MobileBluetooth.devices.plist"
DEVICES_XML="/tmp/bt_devices_readable.xml"
if [ -f "$DEVICES_PLIST" ]; then
  plutil -convert xml1 -o "$DEVICES_XML" "$DEVICES_PLIST" 2>/dev/null
  echo "[*] Devices plist found and converted"
else
  echo "[!] Devices plist not found in $OUTDIR"
fi

for mac in "${MACS[@]}"; do
  mac_lc=$(echo "$mac" | tr '[:upper:]' '[:lower:]')
  mac_dashes=$(echo "$mac_lc" | tr ':' '-')
  echo "[*] Processing MAC: $mac_lc"

  # System plist + devices plist
  FOUND_PLIST=0
  for xml in "$PLIST_XML" "$DEVICES_XML"; do
    [ -f "$xml" ] || continue
    grep -qiE "$mac_lc|$mac_dashes" "$xml" && FOUND_PLIST=1 && break
  done
  echo "    found_plist=$FOUND_PLIST"

  # User-level plists — now in $OUTDIR/user/
  FOUND_BYHOST=0
  for f in "$OUTDIR/user/com.apple.Bluetooth."* "$OUTDIR/user/com.apple.bluetooth.plist" "$OUTDIR/user/com.apple.bluetoothuserd.plist"; do
    [ -f "$f" ] || continue
    plutil -convert xml1 -o /tmp/bt_user_check.xml "$f" 2>/dev/null
    grep -qiE "$mac_lc|$mac_dashes" /tmp/bt_user_check.xml && FOUND_BYHOST=1 && break
  done
  echo "    found_byhost=$FOUND_BYHOST"

  # BLE DB dumps — search all dumped databases
  FOUND_BLE="N/A"
  BLE_DUMPS=("$OUTDIR"/*_dump.sql)
  if [ -f "${BLE_DUMPS[0]}" ]; then
    FOUND_BLE=0
    for dump in "${BLE_DUMPS[@]}"; do
      [ -f "$dump" ] || continue
      grep -qiE "$mac_lc|$mac_dashes" "$dump" && FOUND_BLE=1 && break
    done
  fi
  echo "    found_ble_db=$FOUND_BLE"

  # MAC was found in raw strings T/F
  FOUND_STRINGS="N/A"
  if [ -f "$OUTDIR/raw_strings.txt" ]; then
    FOUND_STRINGS=0
    grep -qiE "$mac_lc|$mac_dashes" "$OUTDIR/raw_strings.txt" && FOUND_STRINGS=1
  fi
  echo "    found_strings=$FOUND_STRINGS"

  # MAC was recovered in SQLite T/F
  RECOVERED="N/A"
  if [ -f "$OUTDIR/recovered.sql" ]; then
    RECOVERED=0
    grep -qiE "$mac_lc|$mac_dashes" "$OUTDIR/recovered.sql" && RECOVERED=1
  fi
  echo "    recovered=$RECOVERED"


  # Count of times MAC was carved (in SQLite)
  if [ -f "$OUTDIR/recovered.sql" ]; then
    CARVED_COUNT=$(grep -ciE "$mac_lc|$mac_dashes" "$OUTDIR/recovered.sql" | wc -l)
  else
    CARVED_COUNT="N/A"
  fi
  echo "    carved_records_count=$CARVED_COUNT"

  NOTES="ok"

  # Number of times MAC was found in FileSystem
  MAC_FS_COUNT=$(awk -F': ' '/^TOTAL_MATCHES_FOUND:/ {print $2}' "$OUTDIR/mac_scan_results.txt" 2>/dev/null)
  MAC_FS_COUNT=${MAC_FS_COUNT:-0}

  # Found after forget
  FOUND_AFTER_FORGET=0
  if [ "$PHASE" == "after_forget" ] && [ "$MAC_FS_COUNT" -gt 0 ]; then
    FOUND_AFTER_FORGET=1
  fi
  echo "    found_after_forget=$FOUND_AFTER_FORGET"

# Wrap EVERY SINGLE VARIABLE in quotes to enforce the 18-column structure
  echo "\"$EXPERIMENT_ID\",\"$PHASE\",\"$TIMESTAMP\",\"$mac_lc\",\"$DEVICE_TYPE\",\"$MACOS_VERSION\",\"$ARCH\",\"$HW_MODEL\",\"$FOUND_PLIST\",\"$FOUND_BYHOST\",\"$FOUND_BLE\",\"$FOUND_STRINGS\",\"$FREELIST\",\"$RECOVERED\",\"$CARVED_COUNT\",\"$NOTES\",\"$MAC_FS_COUNT\",\"$FOUND_AFTER_FORGET\"" >> "$CSV"
done

echo "[+] Logged results to $CSV"