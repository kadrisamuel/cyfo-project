#!/bin/bash
# scan_for_macs.sh — Optimized Forensic MAC Address Scanner
# Recursively searches a directory for specified MAC addresses, dumps detailed matches into a log file,
# and prints a clean, consolidated overview in the terminal.

INPUT_DIR="$1"
shift
MACS=("$@")

if [ -z "$INPUT_DIR" ] || [ ${#MACS[@]} -eq 0 ]; then
  echo "Usage: ./scan_for_macs.sh <directory> <mac1> <mac2> ..."
  exit 1
fi

if [ ! -d "$INPUT_DIR" ]; then
  echo "[!] Error: Directory not found: $INPUT_DIR"
  exit 1
fi

# Clean up input directory path for printing
INPUT_DIR="${INPUT_DIR%/}"
LOG_FILE="$INPUT_DIR/mac_scan_results.txt"

echo "[*] Scanning directory '$INPUT_DIR' for MAC address artifacts..."
echo "[*] Detailed logs will be written to: $LOG_FILE"
echo "" > "$LOG_FILE"

# Initialize global match counter
TOTAL_MATCHES=0

for mac in "${MACS[@]}"; do
  # Standardize casing for casing check
  mac_lc=$(echo "$mac" | tr '[:upper:]' '[:lower:]')
  mac_uc=$(echo "$mac" | tr '[:lower:]' '[:upper:]')
  mac_dash_lc=$(echo "$mac_lc" | tr ':' '-')
  mac_dash_uc=$(echo "$mac_uc" | tr ':' '-')

  echo "======================================================================" >> "$LOG_FILE"
  echo "SEARCH RESULTS FOR MAC: $mac (Variations: $mac_lc, $mac_uc, $mac_dash_lc, $mac_dash_uc)" >> "$LOG_FILE"
  echo "======================================================================" >> "$LOG_FILE"

  echo -e "\033[1;36m🔎 Scanning for MAC: $mac\033[0m"
  
  # Find all unique files containing the MAC address variations
  matched_files=$(grep -ril -e "$mac_lc" -e "$mac_uc" -e "$mac_dash_lc" -e "$mac_dash_uc" "$INPUT_DIR" 2>/dev/null | grep -v "mac_scan_results.txt")

  if [ -z "$matched_files" ]; then
    echo "   ❌ No matches found in any files."
    echo "No matches found." >> "$LOG_FILE"
    echo ""
    continue
  fi

  # Loop through matching files and write detailed matches
  while read -r file; do
    [ -z "$file" ] && continue
    
    # Get total match count in this file (using all variations for accuracy)
    count=$(grep -ci -e "$mac_lc" -e "$mac_uc" -e "$mac_dash_lc" -e "$mac_dash_uc" "$file" 2>/dev/null)
    
    # Add to the running global total
    TOTAL_MATCHES=$((TOTAL_MATCHES + count))
    
    # Write to log file
    echo "----------------------------------------------------------------------" >> "$LOG_FILE"
    echo "File: $file ($count matches)" >> "$LOG_FILE"
    echo "----------------------------------------------------------------------" >> "$LOG_FILE"
    grep -in -e "$mac_lc" -e "$mac_uc" -e "$mac_dash_lc" -e "$mac_dash_uc" "$file" >> "$LOG_FILE" 2>/dev/null
    echo "" >> "$LOG_FILE"

    # Display clean aggregated output in Terminal
    relative_file="${file#$INPUT_DIR/}"
    echo -e "   📍 \033[33m$relative_file\033[0m — \033[1;32m$count match(es)\033[0m"
    
    # Show first 2 matches as preview in terminal (limit line length to 100 chars to avoid wrap clutter)
    echo "      Preview:"
    grep -in -e "$mac_lc" -e "$mac_uc" -e "$mac_dash_lc" -e "$mac_dash_uc" "$file" 2>/dev/null | head -n 2 | while read -r line; do
      truncated_line="${line:0:100}"
      if [ ${#line} -gt 100 ]; then
        truncated_line="${truncated_line}..."
      fi
      echo "        | $truncated_line"
    done
    echo ""

  done <<< "$matched_files"
done

# Write a distinct, parsable footer at the bottom of the log file
echo "======================================================================" >> "$LOG_FILE"
echo "TOTAL_MATCHES_FOUND: $TOTAL_MATCHES" >> "$LOG_FILE"

echo "[+] Scan complete! Full results saved in: $LOG_FILE"