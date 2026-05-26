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

# Create CSV header if not exists
if [ ! -f "$CSV" ]; then
  echo "experiment_id,phase,timestamp,mac,device_type,found_plist,found_byhost,found_ble_db,found_strings,freelist_count,recovered_in_sqlite,notes" > "$CSV"
fi

TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S")
FREELIST=$(cat "$OUTDIR/freelist_count.txt" 2>/dev/null || echo "0")

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
    grep -qi "$mac_lc\|$mac_dashes" "$xml" && FOUND_PLIST=1 && break
  done
  echo "    found_plist=$FOUND_PLIST"

  # User-level plists — now in $OUTDIR/user/
  FOUND_BYHOST=0
  for f in "$OUTDIR/user/com.apple.Bluetooth."* "$OUTDIR/user/com.apple.bluetooth.plist" "$OUTDIR/user/com.apple.bluetoothuserd.plist"; do
    [ -f "$f" ] || continue
    plutil -convert xml1 -o /tmp/bt_user_check.xml "$f" 2>/dev/null
    grep -qi "$mac_lc\|$mac_dashes" /tmp/bt_user_check.xml && FOUND_BYHOST=1 && break
  done
  echo "    found_byhost=$FOUND_BYHOST"

  # BLE DB dump
  FOUND_BLE="N/A"
  if [ -f "$OUTDIR/ble_db_dump.sql" ]; then
    FOUND_BLE=0
    grep -qi "$mac_lc\|$mac_dashes" "$OUTDIR/ble_db_dump.sql" && FOUND_BLE=1
  fi
  echo "    found_ble_db=$FOUND_BLE"

  # Raw strings
  FOUND_STRINGS="N/A"
  if [ -f "$OUTDIR/raw_strings.txt" ]; then
    FOUND_STRINGS=0
    grep -qi "$mac_lc\|$mac_dashes" "$OUTDIR/raw_strings.txt" && FOUND_STRINGS=1
  fi
  echo "    found_strings=$FOUND_STRINGS"

  # Recovered SQL
  RECOVERED="N/A"
  if [ -f "$OUTDIR/recovered.sql" ]; then
    RECOVERED=0
    grep -qi "$mac_lc\|$mac_dashes" "$OUTDIR/recovered.sql" && RECOVERED=1
  fi
  echo "    recovered=$RECOVERED"

  NOTES="ok"
  echo "$EXPERIMENT_ID,$PHASE,$TIMESTAMP,$mac_lc,$DEVICE_TYPE,$FOUND_PLIST,$FOUND_BYHOST,$FOUND_BLE,$FOUND_STRINGS,$FREELIST,$RECOVERED,$NOTES" >> "$CSV"
  echo "    -> row written to $CSV"

done

echo "[+] Logged results to $CSV"