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

# Create CSV header if not exists
if [ ! -f "$CSV" ]; then
  echo "experiment_id,phase,timestamp,mac,device_type,found_plist,found_byhost,found_ble_db,found_strings,freelist_count,recovered_in_sqlite,notes" > "$CSV"
fi

TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S")

# Load freelist count
FREELIST=$(cat "$OUTDIR/freelist_count.txt" 2>/dev/null || echo "0")

for mac in "${MACS[@]}"; do

  # Normalize MAC (lowercase)
  mac_lc=$(echo "$mac" | tr '[:upper:]' '[:lower:]')

  # Search locations
  FOUND_PLIST=$(grep -Ri "$mac_lc" "$OUTDIR/com.apple.Bluetooth.plist" >/dev/null && echo "1" || echo "0")

  FOUND_BYHOST=$(grep -Ri "$mac_lc" "$OUTDIR"/com.apple.Bluetooth.* 2>/dev/null | grep -q ByHost && echo "1" || echo "0")

  FOUND_BLE=$(grep -Ri "$mac_lc" "$OUTDIR/ble_db_dump.sql" >/dev/null && echo "1" || echo "0")

  FOUND_STRINGS=$(grep -Ri "$mac_lc" "$OUTDIR/raw_strings.txt" >/dev/null && echo "1" || echo "0")

  RECOVERED=$(grep -Ri "$mac_lc" "$OUTDIR/recovered.sql" >/dev/null && echo "1" || echo "0")

  echo "$EXPERIMENT_ID,$PHASE,$TIMESTAMP,$mac_lc,$DEVICE_TYPE,$FOUND_PLIST,$FOUND_BYHOST,$FOUND_BLE,$FOUND_STRINGS,$FREELIST,$RECOVERED," >> "$CSV"

done

echo "[+] Logged results to $CSV"