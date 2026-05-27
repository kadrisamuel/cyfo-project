#!/bin/bash
# =============================================================================
# RQ3 — Script 03: Post-Forget Device Snapshot
# Purpose: Immediately after performing Forget Device via System Settings,
#          run this script to capture the post-operation artifact state.
#          Compare output against Script 01 baseline.
# Platform: macOS 26 (Tahoe)
# Usage: Run IMMEDIATELY after Forget Device operation
# =============================================================================

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
OUTPUT_DIR=~/rq3_post_forget_${TIMESTAMP}
mkdir -p "$OUTPUT_DIR"

echo "[*] RQ3 Post-Forget Snapshot — $(date -u)"
echo "[*] Output directory: $OUTPUT_DIR"
echo ""

MOBILE_BT="/Library/Bluetooth/Library/Preferences/com.apple.MobileBluetooth.devices.plist"

# -----------------------------------------------------------------------------
# 1. Hash primary artifact immediately
# -----------------------------------------------------------------------------
echo "[1] Hashing primary artifact (immediate)..."
sudo shasum -a 256 "$MOBILE_BT" \
  > "$OUTPUT_DIR/MobileBluetooth_post_hash.txt" 2>/dev/null \
  || echo "SIP protected — could not hash" > "$OUTPUT_DIR/MobileBluetooth_post_hash.txt"

# -----------------------------------------------------------------------------
# 2. Read primary artifact
# -----------------------------------------------------------------------------
echo "[2] Reading primary artifact..."
sudo plutil -convert xml1 -o "$OUTPUT_DIR/MobileBluetooth_post.xml" \
  "$MOBILE_BT" 2>/dev/null \
  || sudo defaults read "$MOBILE_BT" \
  > "$OUTPUT_DIR/MobileBluetooth_post.txt" 2>/dev/null \
  || echo "SIP protected — could not read" > "$OUTPUT_DIR/MobileBluetooth_post.txt"

# -----------------------------------------------------------------------------
# 3. Check SyncedPreferences — key RQ3 question
# -----------------------------------------------------------------------------
echo "[3] Checking SyncedPreferences for iCloud propagation..."
find ~/Library/SyncedPreferences/ -type f 2>/dev/null \
  > "$OUTPUT_DIR/synced_prefs_post.txt"
if [ ! -s "$OUTPUT_DIR/synced_prefs_post.txt" ]; then
  echo "Empty — no iCloud propagation detected via SyncedPreferences" \
    > "$OUTPUT_DIR/synced_prefs_post.txt"
fi

# -----------------------------------------------------------------------------
# 4. Check Library/Bluetooth
# -----------------------------------------------------------------------------
echo "[4] Checking ~/Library/Bluetooth/..."
find ~/Library/Bluetooth/ -type f 2>/dev/null \
  > "$OUTPUT_DIR/user_library_bluetooth_post.txt" \
  || echo "Empty" > "$OUTPUT_DIR/user_library_bluetooth_post.txt"

# -----------------------------------------------------------------------------
# 5. CloudKit log — Bluetooth activity around forget event
# -----------------------------------------------------------------------------
echo "[5] Capturing CloudKit Bluetooth log (last 5 minutes)..."
log show \
  --predicate 'subsystem contains "cloudkit" AND (eventMessage contains "bluetooth" OR eventMessage contains "Bluetooth")' \
  --last 5m --info 2>/dev/null \
  | grep -E "containerIdentifier|persona|CKModify|Loaded account|error|Error" \
  > "$OUTPUT_DIR/cloudkit_bt_post.txt"

# -----------------------------------------------------------------------------
# 6. audioaccessoryd CloudKit activity
# -----------------------------------------------------------------------------
echo "[6] Capturing audioaccessoryd CloudKit activity (last 5 minutes)..."
log show \
  --predicate 'process == "audioaccessoryd" AND subsystem contains "cloudkit"' \
  --last 5m --info 2>/dev/null \
  | grep -E "containerIdentifier|persona|CKModify|Loaded account" \
  > "$OUTPUT_DIR/audioaccessoryd_cloudkit_post.txt"

# -----------------------------------------------------------------------------
# 7. Keychain — check for BT entry changes
# -----------------------------------------------------------------------------
echo "[7] Checking keychain for Bluetooth entries..."
security find-generic-password -s "Bluetooth" 2>/dev/null \
  > "$OUTPUT_DIR/keychain_bluetooth_post.txt" \
  || echo "No Bluetooth keychain entries" > "$OUTPUT_DIR/keychain_bluetooth_post.txt"

# -----------------------------------------------------------------------------
# 8. Wait and re-check SyncedPreferences (iCloud may be delayed)
# -----------------------------------------------------------------------------
echo "[8] Waiting 60 seconds for delayed iCloud sync..."
sleep 60
echo "    Re-checking SyncedPreferences after delay..."
find ~/Library/SyncedPreferences/ -type f 2>/dev/null \
  > "$OUTPUT_DIR/synced_prefs_post_delayed.txt"
if [ ! -s "$OUTPUT_DIR/synced_prefs_post_delayed.txt" ]; then
  echo "Still empty after 60s — iCloud propagation not detected" \
    > "$OUTPUT_DIR/synced_prefs_post_delayed.txt"
fi

# -----------------------------------------------------------------------------
# 9. Hash all outputs
# -----------------------------------------------------------------------------
echo "[9] Hashing all output files..."
shasum -a 256 "$OUTPUT_DIR"/* > "$OUTPUT_DIR/POST_FORGET_HASHES.txt" 2>/dev/null

echo ""
echo "[*] Post-forget snapshot complete: $OUTPUT_DIR"
echo "[*] Compare against baseline using Script 04"
