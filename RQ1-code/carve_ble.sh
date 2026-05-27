#!/bin/bash
# carve_ble.sh — Robust SQLite database carving helper
# Supports: 
#   1. Direct file input:  ./carve_ble.sh path/to/db.db
#   2. Directory input:    ./carve_ble.sh path/to/state_dir/
#   3. Extra arguments:    ./carve_ble.sh path/to/state_dir/ EXP1 ... (ignores trailing metadata)

TARGET="$1"

if [ -z "$TARGET" ]; then
  echo "Usage: ./carve_ble.sh <db_file_or_directory>"
  exit 1
fi

carve_single_db() {
  local db_file="$1"
  if [ ! -f "$db_file" ]; then
    echo "[!] File not found: $db_file"
    return 1
  fi

  local db_base=$(basename "$db_file")
  local db_dir=$(dirname "$db_file")

  # Determine target output directory (strip /Bluetooth suffix if present)
  local out_dir="$db_dir"
  if [[ "$db_dir" == */Bluetooth ]]; then
    out_dir="${db_dir%/Bluetooth}"
  fi

  mkdir -p "$out_dir"

  echo "[*] Carving database: $db_file"
  echo "    -> Output directory: $out_dir"

  # 1. SQLite Recovery
  echo "    -> Running sqlite recovery..."
  sqlite3 "$db_file" ".recover" > "$out_dir/recovered.sql" 2>/dev/null
  cp "$out_dir/recovered.sql" "$out_dir/${db_base%.db}_recovered.sql" 2>/dev/null

  # 2. Extract Strings
  echo "    -> Extracting raw strings..."
  strings "$db_file" > "$out_dir/raw_strings.txt" 2>/dev/null
  cp "$out_dir/raw_strings.txt" "$out_dir/${db_base%.db}_strings.txt" 2>/dev/null

  echo "[+] Carving complete for $db_base"
}

if [ -d "$TARGET" ]; then
  echo "[*] Directory provided. Searching for SQLite databases under: $TARGET"
  # Find all .db files under directory (depth 3 to prevent infinite loops, but recursive)
  DB_FILES=$(find "$TARGET" -type f -name "*.db" 2>/dev/null)
  
  if [ -z "$DB_FILES" ]; then
    echo "[!] No .db files found under directory: $TARGET"
    exit 1
  fi

  for db in $DB_FILES; do
    carve_single_db "$db"
  done
elif [ -f "$TARGET" ]; then
  carve_single_db "$TARGET"
else
  echo "[!] Error: target is neither a valid file nor directory: $TARGET"
  exit 1
fi