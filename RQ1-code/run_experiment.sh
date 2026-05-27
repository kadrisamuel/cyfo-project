#!/bin/bash
# run_experiment.sh — Stateful Bluetooth Forensic Orchestrator
# Guides researchers step-by-step through experiments, ensuring clean reboots,
# automatic carving, logging, state comparisons, and error prevention.

STATE_FILE=".experiment_state.sh"

# Standard color codes
RED="\033[31m"
GREEN="\033[32m"
YELLOW="\033[33m"
BLUE="\033[34m"
CYAN="\033[36m"
BOLD="\033[1m"
NC="\033[0m"

# Print header helper
print_header() {
  echo -e "${CYAN}======================================================================${NC}"
  echo -e "       ${BOLD}🍎 MACOS BLUETOOTH FORENSIC EXPERIMENTATION SUITE${NC}"
  echo -e "${CYAN}======================================================================${NC}"
}

# Load state if it exists
if [ -f "$STATE_FILE" ]; then
  source "$STATE_FILE"
else
  STATE="NONE"
fi

# Command-line abort handling
if [[ "$1" == "--abort" ]] || [[ "$1" == "-a" ]] || [[ "$1" == "--cancel" ]]; then
  if [ -f "$STATE_FILE" ]; then
    source "$STATE_FILE"
    rm -f "$STATE_FILE"
    echo -e "${GREEN}[+] Aborted active experiment '$EXP_ID' and cleared state file.${NC}"
  else
    echo -e "${YELLOW}[*] No active experiment state to abort.${NC}"
  fi
  exit 0
fi

# Interactive check to abort mid-run
if [ "$STATE" != "NONE" ]; then
  print_header
  echo -e "${YELLOW}[!] An active experiment is currently in progress:${NC}"
  echo -e "    ID:            ${BOLD}$EXP_ID${NC}"
  echo -e "    Device:        $FRIENDLY_NAME ($DEVICE_TYPE)"
  echo -e "    MAC:           $MAC_ADDRESS"
  echo -e "    Current Phase: $STATE"
  echo ""
  echo -e "What would you like to do?"
  echo -e "  [1] Continue active experiment (Default)"
  echo -e "  [2] Abort/Cancel active experiment"
  echo ""
  read -p "Select option [1-2, default 1]: " OPTION
  if [ "$OPTION" == "2" ]; then
    echo -e "${RED}[*] Aborting active experiment...${NC}"
    rm -f "$STATE_FILE"
    echo -e "${GREEN}[+] Active experiment state has been cleared successfully. You can now start a new one!${NC}"
    exit 0
  fi
fi

case "$STATE" in
  "NONE")
    print_header
    echo -e "${BLUE}[*] No active experiment state found. Let's initialize a new one!${NC}"
    echo -e "${YELLOW}Please make sure your Bluetooth test device is forgotten from this computer before proceeding.${NC}"
    echo ""
    
    # Prompt for Experiment Details
    read -p "Enter Experiment ID [e.g. EXP1]: " EXP_ID
    if [ -z "$EXP_ID" ]; then EXP_ID="EXP_TEMP"; fi

    read -p "Enter Device Type [e.g., mouse, keyboard, headphones, speaker]: " DEVICE_TYPE
    if [ -z "$DEVICE_TYPE" ]; then DEVICE_TYPE="unknown"; fi

    read -p "Enter Target MAC Address [e.g. F8:4D:89:4C:79:D7]: " MAC_ADDRESS
    if [ -z "$MAC_ADDRESS" ]; then
      echo -e "${RED}[!] Error: MAC Address is required.${NC}"
      exit 1
    fi

    read -p "Enter Friendly Name [e.g. Kadri's AirPods]: " FRIENDLY_NAME
    if [ -z "$FRIENDLY_NAME" ]; then FRIENDLY_NAME="Test Device"; fi

    echo ""
    echo -e "${YELLOW}--- Experiment Profile ---${NC}"
    echo -e "    ID:            $EXP_ID"
    echo -e "    Device:        $FRIENDLY_NAME ($DEVICE_TYPE)"
    echo -e "    MAC:           $MAC_ADDRESS"
    echo -e "${YELLOW}--------------------------${NC}"
    echo ""
    read -p "Initialize this experiment and clean the Bluetooth subsystem? [y/N]: " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[yY]$ ]]; then
      echo -e "${RED}[!] Canceled.${NC}"
      exit 0
    fi

    # Write initial variables to state file
    cat << EOF > "$STATE_FILE"
STATE="PENDING_BASELINE"
EXP_ID="$EXP_ID"
DEVICE_TYPE="$DEVICE_TYPE"
MAC_ADDRESS="$MAC_ADDRESS"
FRIENDLY_NAME="$FRIENDLY_NAME"
EOF

    echo -e "${BLUE}[*] Running reset_bt.sh (requires sudo credentials)...${NC}"
    sudo ./reset_bt.sh

    echo ""
    echo -e "${GREEN}====================== STEP 1 COMPLETE ======================${NC}"
    echo -e "${YELLOW}[!] Bluetooth subsystem has been cleaned and backed up.${NC}"
    echo -e "${BOLD}[!] CRITICAL NEXT STEP: Please RESTART your computer now!${NC}"
    echo -e "${YELLOW}    After logging back in, return to Terminal and run this script again:${NC}"
    echo -e "    ${BOLD}./run_experiment.sh${NC}"
    echo -e "${GREEN}=============================================================${NC}"
    echo ""
    ;;

  "PENDING_BASELINE")
    print_header
    echo -e "${BLUE}[*] Active Experiment: ${BOLD}$EXP_ID ($FRIENDLY_NAME)${NC}"
    echo -e "${BLUE}[*] Phase: Capture Post-Reboot Clean Baseline${NC}"
    echo ""

    read -p "Has your computer been rebooted since the reset? [y/N]: " REBOOTED
    if [[ ! "$REBOOTED" =~ ^[yY]$ ]]; then
      echo -e "${YELLOW}[!] Warning: It is highly recommended to reboot before capturing the baseline.${NC}"
      read -p "Do you want to continue anyway? [y/N]: " FORCE_CONTINUE
      if [[ ! "$FORCE_CONTINUE" =~ ^[yY]$ ]]; then
        echo -e "${RED}[!] Aborted. Please reboot and rerun this script.${NC}"
        exit 0
      fi
    fi

    echo -e "${BLUE}[*] Collecting baseline state...${NC}"
    ./collect_state.sh baseline_clean

    # Find the newly captured baseline directory
    BASELINE_DIR=$(ls -td baseline_clean_* 2>/dev/null | head -n 1)
    if [ -z "$BASELINE_DIR" ]; then
      echo -e "${RED}[!] Error: Could not locate baseline_clean directory!${NC}"
      exit 1
    fi

    echo -e "${BLUE}[*] Logging baseline results to results.csv...${NC}"
    ./log_results.sh "$BASELINE_DIR" "$EXP_ID" "baseline" "$DEVICE_TYPE" "$MAC_ADDRESS"

    # Update state file
    cat << EOF > "$STATE_FILE"
STATE="PENDING_PAIRED"
EXP_ID="$EXP_ID"
DEVICE_TYPE="$DEVICE_TYPE"
MAC_ADDRESS="$MAC_ADDRESS"
FRIENDLY_NAME="$FRIENDLY_NAME"
BASELINE_DIR="$BASELINE_DIR"
EOF

    echo ""
    echo -e "${GREEN}====================== STEP 2 COMPLETE ======================${NC}"
    echo -e "${GREEN}[+] Baseline captured: ${BOLD}$BASELINE_DIR${NC}"
    echo -e "${BOLD}[!] CRITICAL NEXT STEP:${NC}"
    echo -e "    1. Pair and connect your device ${BOLD}'$FRIENDLY_NAME' ($MAC_ADDRESS)${NC}."
    echo -e "    2. Verify it is connected and working."
    echo -e "    3. Once connected, run this script again to record the active state:"
    echo -e "       ${BOLD}./run_experiment.sh${NC}"
    echo -e "${GREEN}=============================================================${NC}"
    echo ""
    ;;

  "PENDING_PAIRED")
    print_header
    echo -e "${BLUE}[*] Active Experiment: ${BOLD}$EXP_ID ($FRIENDLY_NAME)${NC}"
    echo -e "${BLUE}[*] Phase: Capture Active Connection State${NC}"
    echo ""

    read -p "Is '$FRIENDLY_NAME' actively connected to this Mac? [y/N]: " CONNECTED
    if [[ ! "$CONNECTED" =~ ^[yY]$ ]]; then
      echo -e "${RED}[!] Please connect the device first, then run this script again.${NC}"
      exit 0
    fi

    echo -e "${BLUE}[*] Collecting paired state...${NC}"
    ./collect_state.sh after_pair

    # Find newly captured paired directory
    PAIRED_DIR=$(ls -td after_pair_* 2>/dev/null | head -n 1)
    if [ -z "$PAIRED_DIR" ]; then
      echo -e "${RED}[!] Error: Could not locate after_pair directory!${NC}"
      exit 1
    fi

    echo -e "${BLUE}[*] Logging paired results to results.csv...${NC}"
    ./log_results.sh "$PAIRED_DIR" "$EXP_ID" "paired" "$DEVICE_TYPE" "$MAC_ADDRESS"

    # Update state file
    cat << EOF > "$STATE_FILE"
STATE="PENDING_FORGOTTEN"
EXP_ID="$EXP_ID"
DEVICE_TYPE="$DEVICE_TYPE"
MAC_ADDRESS="$MAC_ADDRESS"
FRIENDLY_NAME="$FRIENDLY_NAME"
BASELINE_DIR="$BASELINE_DIR"
PAIRED_DIR="$PAIRED_DIR"
EOF

    echo ""
    echo -e "${GREEN}====================== STEP 3 COMPLETE ======================${NC}"
    echo -e "${GREEN}[+] Paired state captured: ${BOLD}$PAIRED_DIR${NC}"
    echo -e "${BOLD}[!] CRITICAL NEXT STEP:${NC}"
    echo -e "    1. Open System Settings -> Bluetooth."
    echo -e "    2. Click the 'i' next to your device and click ${RED}${BOLD}'Forget This Device'${NC}."
    echo -e "    3. Turn Bluetooth OFF and ON again to flush caches."
    echo -e "    4. Run this script again to capture the forgotten state & carve SQLite records:"
    echo -e "       ${BOLD}./run_experiment.sh${NC}"
    echo -e "${GREEN}=============================================================${NC}"
    echo ""
    ;;

  "PENDING_FORGOTTEN")
    print_header
    echo -e "${BLUE}[*] Active Experiment: ${BOLD}$EXP_ID ($FRIENDLY_NAME)${NC}"
    echo -e "${BLUE}[*] Phase: Capture Forgotten State & Auto-Carving${NC}"
    echo ""

    read -p "Have you clicked 'Forget This Device' for '$FRIENDLY_NAME'? [y/N]: " FORGOTTEN
    if [[ ! "$FORGOTTEN" =~ ^[yY]$ ]]; then
      echo -e "${RED}[!] Please forget the device first, then run this script again.${NC}"
      exit 0
    fi

    echo -e "${BLUE}[*] Collecting forgotten state...${NC}"
    ./collect_state.sh after_forget

    # Find newly captured forgotten directory
    FORGOTTEN_DIR=$(ls -td after_forget_* 2>/dev/null | head -n 1)
    if [ -z "$FORGOTTEN_DIR" ]; then
      echo -e "${RED}[!] Error: Could not locate after_forget directory!${NC}"
      exit 1
    fi

    # 1. Auto SQLite Carving
    echo -e "${BLUE}[*] Automatically carving SQLite databases in $FORGOTTEN_DIR...${NC}"
    ./carve_ble.sh "$FORGOTTEN_DIR"

    # 2. Auto Log Results
    echo -e "${BLUE}[*] Logging forgotten & carved results to results.csv...${NC}"
    ./log_results.sh "$FORGOTTEN_DIR" "$EXP_ID" "after_forget" "$DEVICE_TYPE" "$MAC_ADDRESS"

    # 3. Auto State Comparisons
    echo -e "${BLUE}[*] Performing smart structural comparison (Baseline vs Forgotten)...${NC}"
    ./compare_states.sh "$BASELINE_DIR" "$FORGOTTEN_DIR"
    # Move comparative files into the forgotten directory to keep the root tidy
    if [ -f "comparison_summary.txt" ]; then
      mv comparison_summary.txt comparison.diff "$FORGOTTEN_DIR/" 2>/dev/null
    fi

    # 4. Auto MAC Scan
    echo -e "${BLUE}[*] Scanning forgotten state for raw MAC address remnants...${NC}"
    ./scan_for_macs.sh "$FORGOTTEN_DIR" "$MAC_ADDRESS"

    # Complete clean up
    rm -f "$STATE_FILE"

    echo ""
    echo -e "${GREEN}======================================================================${NC}"
    echo -e "       ${GREEN}${BOLD}🎉 EXPERIMENT $EXP_ID SUCCESSFULLY COMPLETED!${NC}"
    echo -e "${GREEN}======================================================================${NC}"
    echo -e "All states captured, logged, carved, compared, and audited:"
    echo -e "  📍 ${BOLD}Baseline Dir:${NC}    $BASELINE_DIR"
    echo -e "  📍 ${BOLD}Paired Dir:${NC}      $PAIRED_DIR"
    echo -e "  📍 ${BOLD}Forgotten Dir:${NC}   $FORGOTTEN_DIR"
    echo ""
    echo -e "📝 ${BOLD}Key Assets Created / Updated:${NC}"
    echo -e "  1. ${CYAN}results.csv${NC} — Cumulative metrics sheet."
    echo -e "  2. ${CYAN}$FORGOTTEN_DIR/comparison_summary.txt${NC} — Smart diff of baseline vs forget."
    echo -e "  3. ${CYAN}$FORGOTTEN_DIR/mac_scan_results.txt${NC} — Raw search for MAC occurrences."
    if [ -f "$FORGOTTEN_DIR/recovered.sql" ]; then
      echo -e "  4. ${CYAN}$FORGOTTEN_DIR/recovered.sql${NC} — SQLite carved/recovered database dump."
    fi
    echo -e "${GREEN}======================================================================${NC}"
    echo ""
    ;;
esac
