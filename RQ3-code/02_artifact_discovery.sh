#!/bin/bash
# =============================================================================
# RQ3 — Script 02: Bluetooth Artifact Discovery
# Purpose: Discover all Bluetooth-related files on the system using multiple
#          search methods. Useful when standard locations are empty (macOS 26).
# Platform: macOS 26 (Tahoe)
# =============================================================================

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
OUTPUT_DIR=~/rq3_discovery_${TIMESTAMP}
mkdir -p "$OUTPUT_DIR"

echo "[*] RQ3 Artifact Discovery — $(date -u)"
echo "[*] Output directory: $OUTPUT_DIR"
echo ""

# -----------------------------------------------------------------------------
# 1. OS Version
# -----------------------------------------------------------------------------
echo "[1] Recording OS version..."
sw_vers > "$OUTPUT_DIR/os_version.txt"

# -----------------------------------------------------------------------------
# 2. Broad filesystem search for Bluetooth-named files
# -----------------------------------------------------------------------------
echo "[2] Broad filesystem search (excluding system frameworks)..."
sudo find /Library /private/var /System/Library/Bluetooth \
  \( -name "*[Bb]luetooth*" -o -name "*[Bb]onding*" -o -name "*[Pp]airing*" \) \
  2>/dev/null \
  | grep -v "\.lproj\|/System/Library/Frameworks\|/System/Library/CoreServices\|\.app\|\.kext\|\.bundle\|\.framework" \
  > "$OUTPUT_DIR/bt_file_discovery.txt"

# -----------------------------------------------------------------------------
# 3. Spotlight search
# -----------------------------------------------------------------------------
echo "[3] Spotlight search for Bluetooth files..."
sudo mdfind -name "Bluetooth" 2>/dev/null \
  | grep -v "\.app\|\.framework\|\.lproj\|\.kext\|\.bundle\|/System/Library" \
  > "$OUTPUT_DIR/bt_spotlight.txt"

# -----------------------------------------------------------------------------
# 4. bluetoothd filesystem activity (live — run briefly)
# -----------------------------------------------------------------------------
echo "[4] Sampling bluetoothd filesystem activity (10 seconds)..."
sudo timeout 10 fs_usage -w bluetoothd 2>/dev/null \
  | grep -v "THROTTLED" \
  > "$OUTPUT_DIR/bluetoothd_fsusage.txt" || true

# -----------------------------------------------------------------------------
# 5. Check /Library/Bluetooth/ directory structure
# -----------------------------------------------------------------------------
echo "[5] Checking /Library/Bluetooth/ structure..."
sudo find /Library/Bluetooth/ -type f 2>/dev/null \
  > "$OUTPUT_DIR/library_bluetooth_files.txt" \
  || echo "SIP protected or empty" > "$OUTPUT_DIR/library_bluetooth_files.txt"

# -----------------------------------------------------------------------------
# 6. Check private var locations
# -----------------------------------------------------------------------------
echo "[6] Checking /private/var/db/ for Bluetooth data..."
sudo find /private/var/db/ -name "*[Bb]luetooth*" 2>/dev/null \
  > "$OUTPUT_DIR/private_var_db.txt" \
  || echo "Not found or not accessible" > "$OUTPUT_DIR/private_var_db.txt"

# -----------------------------------------------------------------------------
# 7. Read primary artifact if found
# -----------------------------------------------------------------------------
MOBILE_BT="/Library/Bluetooth/Library/Preferences/com.apple.MobileBluetooth.devices.plist"
echo "[7] Attempting to read primary artifact: $MOBILE_BT"
if sudo test -f "$MOBILE_BT" 2>/dev/null; then
  echo "    File exists — attempting read..."
  sudo /usr/libexec/PlistBuddy -c "Print" "$MOBILE_BT" \
    > "$OUTPUT_DIR/MobileBluetooth_plistbuddy.txt" 2>/dev/null \
    || sudo defaults read "$MOBILE_BT" \
    > "$OUTPUT_DIR/MobileBluetooth_defaults.txt" 2>/dev/null \
    || echo "    Could not read — SIP protected" > "$OUTPUT_DIR/MobileBluetooth_read_result.txt"
else
  echo "    File not found at expected location" > "$OUTPUT_DIR/MobileBluetooth_read_result.txt"
fi

# -----------------------------------------------------------------------------
# 8. Hash outputs
# -----------------------------------------------------------------------------
echo "[8] Hashing output files..."
shasum -a 256 "$OUTPUT_DIR"/* > "$OUTPUT_DIR/DISCOVERY_HASHES.txt" 2>/dev/null

echo ""
echo "[*] Discovery complete: $OUTPUT_DIR"
