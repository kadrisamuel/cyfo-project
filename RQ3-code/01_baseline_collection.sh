#!/bin/bash
# =============================================================================
# RQ3 — Script 01: Baseline Artifact Collection
# Purpose: Capture state of all Bluetooth artifact locations before any
#          pairing or iCloud activity. Run this BEFORE signing into Apple ID.
# Platform: macOS 26 (Tahoe) — paths differ from earlier macOS versions
# =============================================================================

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
OUTPUT_DIR=~/rq3_baseline_${TIMESTAMP}
mkdir -p "$OUTPUT_DIR"

echo "[*] RQ3 Baseline Collection — $(date -u)"
echo "[*] Output directory: $OUTPUT_DIR"
echo ""

# -----------------------------------------------------------------------------
# 1. iCloud Account State
# -----------------------------------------------------------------------------
echo "[1] Checking iCloud account state..."
defaults read MobileMeAccounts 2>/dev/null \
  | grep -E "AccountID|iCloudQuota|Enabled" \
  > "$OUTPUT_DIR/icloud_account.txt" \
  || echo "No iCloud account found" > "$OUTPUT_DIR/icloud_account.txt"

# -----------------------------------------------------------------------------
# 2. System-level Bluetooth plist (legacy location)
# -----------------------------------------------------------------------------
echo "[2] Reading system Bluetooth plist (legacy location)..."
sudo plutil -convert xml1 -o "$OUTPUT_DIR/system_bluetooth_legacy.xml" \
  /Library/Preferences/com.apple.Bluetooth.plist 2>/dev/null \
  || echo "Not found or not readable" > "$OUTPUT_DIR/system_bluetooth_legacy.xml"

# -----------------------------------------------------------------------------
# 3. User-level Bluetooth plist
# -----------------------------------------------------------------------------
echo "[3] Reading user Bluetooth plist..."
defaults read ~/Library/Preferences/com.apple.Bluetooth.plist 2>/dev/null \
  > "$OUTPUT_DIR/user_bluetooth.txt" \
  || echo "Empty or not found" > "$OUTPUT_DIR/user_bluetooth.txt"

# -----------------------------------------------------------------------------
# 4. Primary artifact location (macOS 26)
# -----------------------------------------------------------------------------
echo "[4] Reading primary MobileBluetooth devices plist (macOS 26 location)..."
MOBILE_BT="/Library/Bluetooth/Library/Preferences/com.apple.MobileBluetooth.devices.plist"
if sudo test -f "$MOBILE_BT"; then
  sudo plutil -convert xml1 -o "$OUTPUT_DIR/MobileBluetooth_devices.xml" "$MOBILE_BT" 2>/dev/null \
    || sudo defaults read "$MOBILE_BT" > "$OUTPUT_DIR/MobileBluetooth_devices.txt" 2>/dev/null \
    || echo "SIP protected — could not read" > "$OUTPUT_DIR/MobileBluetooth_devices.txt"
  sudo shasum -a 256 "$MOBILE_BT" > "$OUTPUT_DIR/MobileBluetooth_hash.txt" 2>/dev/null \
    || echo "SIP protected — could not hash" > "$OUTPUT_DIR/MobileBluetooth_hash.txt"
else
  echo "File not found" > "$OUTPUT_DIR/MobileBluetooth_devices.txt"
fi

# -----------------------------------------------------------------------------
# 5. Library/Bluetooth directory inventory
# -----------------------------------------------------------------------------
echo "[5] Inventorying ~/Library/Bluetooth/..."
find ~/Library/Bluetooth/ -type f 2>/dev/null \
  > "$OUTPUT_DIR/user_library_bluetooth.txt" \
  || echo "Empty or not found" > "$OUTPUT_DIR/user_library_bluetooth.txt"

echo "[5b] Inventorying /Library/Bluetooth/ (system)..."
sudo find /Library/Bluetooth/ -type f 2>/dev/null \
  > "$OUTPUT_DIR/system_library_bluetooth.txt" \
  || echo "SIP protected or empty" > "$OUTPUT_DIR/system_library_bluetooth.txt"

# -----------------------------------------------------------------------------
# 6. SyncedPreferences (iCloud sync channel)
# -----------------------------------------------------------------------------
echo "[6] Checking SyncedPreferences..."
find ~/Library/SyncedPreferences/ -type f 2>/dev/null \
  > "$OUTPUT_DIR/synced_prefs.txt" \
  || echo "Empty or not found" > "$OUTPUT_DIR/synced_prefs.txt"

# -----------------------------------------------------------------------------
# 7. iCloud containers inventory
# -----------------------------------------------------------------------------
echo "[7] Inventorying iCloud containers..."
ls ~/Library/Mobile\ Documents/ 2>/dev/null \
  > "$OUTPUT_DIR/icloud_containers.txt" \
  || echo "No iCloud containers" > "$OUTPUT_DIR/icloud_containers.txt"

# -----------------------------------------------------------------------------
# 8. Keychain Bluetooth entries
# -----------------------------------------------------------------------------
echo "[8] Checking keychain for Bluetooth entries..."
security find-generic-password -s "Bluetooth" 2>/dev/null \
  > "$OUTPUT_DIR/keychain_bluetooth.txt" \
  || echo "No Bluetooth keychain entries" > "$OUTPUT_DIR/keychain_bluetooth.txt"

# -----------------------------------------------------------------------------
# 9. Anchor log position for later diff
# -----------------------------------------------------------------------------
echo "[9] Anchoring Bluetooth log position..."
log show --predicate 'subsystem == "com.apple.bluetooth"' \
  --last 1m --style syslog 2>/dev/null | tail -5 \
  > "$OUTPUT_DIR/bt_log_anchor.txt"

# -----------------------------------------------------------------------------
# 10. Hash all output files for chain of custody
# -----------------------------------------------------------------------------
echo "[10] Hashing all output files..."
shasum -a 256 "$OUTPUT_DIR"/* > "$OUTPUT_DIR/BASELINE_HASHES.txt" 2>/dev/null

echo ""
echo "[*] Baseline collection complete: $OUTPUT_DIR"
echo "[*] Timestamp: $TIMESTAMP"
