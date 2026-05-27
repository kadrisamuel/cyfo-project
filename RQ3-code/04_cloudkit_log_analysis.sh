#!/bin/bash
# RQ3 — Script 04: CloudKit Bluetooth Log Analysis
# Monitor and capture CloudKit activity for all Bluetooth-related
# containers. Identifies sync agents, container identifiers, and
# authentication status.
# Platform: macOS 26 (Tahoe)
# Usage: Run during or after pairing/forget operations

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%SZ")
OUTPUT_DIR=~/rq3_cloudkit_${TIMESTAMP}
mkdir -p "$OUTPUT_DIR"

echo "[*] RQ3 CloudKit Bluetooth Analysis — $(date -u)"
echo "[*] Output directory: $OUTPUT_DIR"
echo ""

# Identify all Bluetooth CloudKit containers (last 10 min)
echo "[1] Identifying Bluetooth CloudKit containers..."
log show \
  --predicate 'subsystem contains "cloudkit" AND (eventMessage contains "bluetooth" OR eventMessage contains "Bluetooth")' \
  --last 10m --info 2>/dev/null \
  | grep "containerIdentifier" \
  | grep -oE 'containerIdentifier=[^,>]+' \
  | sort | uniq -c | sort -rn \
  > "$OUTPUT_DIR/container_identifiers.txt"

echo "    Containers found:"
cat "$OUTPUT_DIR/container_identifiers.txt"
echo ""

# audioaccessoryd — primary Bluetooth sync agent
echo "[2] Capturing audioaccessoryd CloudKit activity (last 10 min)..."
log show \
  --predicate 'process == "audioaccessoryd" AND subsystem contains "cloudkit"' \
  --last 10m --info 2>/dev/null \
  | grep -E "containerIdentifier|persona|CKModify|Loaded account|error|Error|fail|Fail" \
  > "$OUTPUT_DIR/audioaccessoryd_summary.txt"

# Check persona status for each container
echo "[3] Checking persona status (null = unauthenticated)..."
log show \
  --predicate 'process == "audioaccessoryd" AND subsystem contains "cloudkit"' \
  --last 10m --info 2>/dev/null \
  | grep "Determined the persona" \
  | grep -oE 'containerIdentifier=[^,>]+.*\): [^>]+' \
  | head -20 \
  > "$OUTPUT_DIR/persona_status.txt"

# CKModifySubscriptionsOperation activity
echo "[4] Capturing subscription operations..."
log show \
  --predicate 'process == "audioaccessoryd" AND subsystem contains "cloudkit"' \
  --last 10m --info 2>/dev/null \
  | grep "CKModifySubscriptionsOperation" \
  > "$OUTPUT_DIR/subscription_operations.txt"

echo "    Subscription operations count: $(wc -l < "$OUTPUT_DIR/subscription_operations.txt")"

# cloudd activity for Bluetooth containers
echo "[5] Capturing cloudd Bluetooth activity..."
log show \
  --predicate 'process == "cloudd" AND subsystem contains "cloudkit"' \
  --last 10m --info 2>/dev/null \
  | grep -i "bluetooth" \
  > "$OUTPUT_DIR/cloudd_bluetooth.txt"

# Error analysis
echo "[6] Analysing errors..."
log show \
  --predicate 'subsystem contains "cloudkit" AND (eventMessage contains "bluetooth" OR eventMessage contains "Bluetooth")' \
  --last 10m --info 2>/dev/null \
  | grep -iE "error|fail|denied|unauthori" \
  > "$OUTPUT_DIR/errors.txt"

echo "    Errors found: $(wc -l < "$OUTPUT_DIR/errors.txt")"

# Process crash pattern (repeated PID increments = crash loop)
echo "[7] Checking for audioaccessoryd crash loop pattern..."
log show \
  --predicate 'process == "audioaccessoryd" AND subsystem contains "cloudkit"' \
  --last 10m --info 2>/dev/null \
  | awk '{print $7}' \
  | sort -un \
  > "$OUTPUT_DIR/audioaccessoryd_pids.txt"

PID_COUNT=$(wc -l < "$OUTPUT_DIR/audioaccessoryd_pids.txt")
echo "    Unique audioaccessoryd PIDs in last 10min: $PID_COUNT"
if [ "$PID_COUNT" -gt 5 ]; then
  echo "    WARNING: High PID count suggests crash loop — auth likely failing"
fi

# Live stream option
echo ""
echo "[8] To stream live CloudKit Bluetooth activity, run:"
echo "    log stream \\"
echo "      --predicate 'subsystem contains \"cloudkit\" AND (eventMessage contains \"bluetooth\" OR process == \"audioaccessoryd\")' \\"
echo "      --level info --style syslog | tee ~/rq3_live_cloudkit.log"

# Hash outputs
shasum -a 256 "$OUTPUT_DIR"/* > "$OUTPUT_DIR/CLOUDKIT_HASHES.txt" 2>/dev/null

echo ""
echo "[*] CloudKit analysis complete: $OUTPUT_DIR"
