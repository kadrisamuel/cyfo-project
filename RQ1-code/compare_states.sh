#!/bin/bash
# compare_states.sh — Upgraded Forensic State Comparator
# Auto-converts binary plists to XML, removes binary/hash noise, and outputs a clean diff and structured summary.

BASELINE="$1"
AFTER="$2"

if [ -z "$BASELINE" ] || [ -z "$AFTER" ]; then
  echo "Usage: ./compare_states.sh <baseline_dir> <after_dir>"
  exit 1
fi

if [ ! -d "$BASELINE" ] || [ ! -d "$AFTER" ]; then
  echo "[!] Error: Both paths must be valid directories."
  exit 1
fi

echo "[*] Comparing forensic states:"
echo "    Baseline: $BASELINE"
echo "    After:    $AFTER"

# Create clean temporary directories for processing
TEMP_BASE="./.tmp_compare_base"
TEMP_AFTER="./.tmp_compare_after"

rm -rf "$TEMP_BASE" "$TEMP_AFTER"
mkdir -p "$TEMP_BASE" "$TEMP_AFTER"

prepare_temp_dir() {
  local src_dir="$1"
  local dest_dir="$2"

  # Copy everything
  cp -R "$src_dir/"* "$dest_dir/" 2>/dev/null

  # Remove binary/hash noise
  find "$dest_dir" -type f -name "*.db" -delete 2>/dev/null      # Ignore raw SQLite binaries (dumps are compared)
  find "$dest_dir" -type f -name "*.sha256" -delete 2>/dev/null  # Ignore hash files
  find "$dest_dir" -type f -name "*.shm" -delete 2>/dev/null     # Ignore DB WAL index
  find "$dest_dir" -type f -name "*.wal" -delete 2>/dev/null     # Ignore DB WAL journal

  # Recursively convert all plists in destination to human-readable XML
  find "$dest_dir" -type f | while read -r file; do
    # Check if plist (or tries to convert it)
    if [[ "$file" == *.plist ]] || [[ $(file -b "$file" 2>/dev/null) == *"Apple binary property list"* ]]; then
      plutil -convert xml1 "$file" 2>/dev/null
    fi
  done
}

echo "[*] Normalizing states (converting plists to XML, removing binary noise)..."
prepare_temp_dir "$BASELINE" "$TEMP_BASE"
prepare_temp_dir "$AFTER" "$TEMP_AFTER"

# Output structured summary
REPORT="comparison_summary.txt"
{
  echo "======================================================================"
  echo "              FORENSIC STATE COMPARISON REPORT"
  echo "======================================================================"
  echo "Generated: $(date)"
  echo "Baseline State: $BASELINE"
  echo "After State:    $AFTER"
  echo "----------------------------------------------------------------------"
  echo ""
  echo "--- FILE INVENTORY CHANGES ---"
} > "$REPORT"

# Compare folder contents at file level
ADDED=$(diff -qr "$TEMP_BASE" "$TEMP_AFTER" | grep -i "Only in $TEMP_AFTER" | sed "s|Only in $TEMP_AFTER|Added file/folder:|g")
REMOVED=$(diff -qr "$TEMP_BASE" "$TEMP_AFTER" | grep -i "Only in $TEMP_BASE" | sed "s|Only in $TEMP_BASE|Removed file/folder:|g")
CHANGED=$(diff -qr "$TEMP_BASE" "$TEMP_AFTER" | grep -i "differ$" | sed "s|Files $TEMP_BASE/\(.*\) and $TEMP_AFTER/\(.*\) differ|Modified file: \1|g")

{
  if [ -n "$REMOVED" ]; then
    echo "Files Removed in 'After' State:"
    echo "$REMOVED"
    echo ""
  else
    echo "No files were removed."
    echo ""
  fi

  if [ -n "$ADDED" ]; then
    echo "Files Added in 'After' State:"
    echo "$ADDED"
    echo ""
  else
    echo "No files were added."
    echo ""
  fi

  if [ -n "$CHANGED" ]; then
    echo "Modified Files (Structure or Content changes):"
    echo "$CHANGED"
    echo ""
  else
    echo "No files were modified."
    echo ""
  fi
  
  echo "----------------------------------------------------------------------"
  echo "--- DETAILED CONTENT DIFFERENCES ---"
  echo ""
} >> "$REPORT"

# Detailed diff of contents
diff -ruN "$TEMP_BASE" "$TEMP_AFTER" > .tmp_diff 2>/dev/null
# Clean up temp path strings inside diff to make it relative to experiment directories
sed -i '' "s|$TEMP_BASE/|/|g" .tmp_diff 2>/dev/null
sed -i '' "s|$TEMP_AFTER/|/|g" .tmp_diff 2>/dev/null

cat .tmp_diff >> "$REPORT"
rm -f .tmp_diff

# Save pure diff file too
diff -ruN "$TEMP_BASE" "$TEMP_AFTER" > comparison.diff 2>/dev/null
sed -i '' "s|$TEMP_BASE/||g" comparison.diff 2>/dev/null
sed -i '' "s|$TEMP_AFTER/||g" comparison.diff 2>/dev/null

# Clean up temporary folders
rm -rf "$TEMP_BASE" "$TEMP_AFTER"

echo "[+] Comparison complete!"
echo "    -> Detailed textual diff saved to:  comparison.diff"
echo "    -> Structured forensic report saved to: $REPORT"
echo ""
echo "==================== INVENTORY CHANGES ===================="
if [ -n "$REMOVED" ]; then
  echo -e "\033[31m[Removed]\033[0m"
  echo "$REMOVED"
fi
if [ -n "$ADDED" ]; then
  echo -e "\033[32m[Added]\033[0m"
  echo "$ADDED"
fi
if [ -n "$CHANGED" ]; then
  echo -e "\033[34m[Modified]\033[0m"
  echo "$CHANGED"
fi
echo "==========================================================="