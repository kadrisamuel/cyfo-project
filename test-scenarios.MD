# Test Scenarios

## RQ1 — Persistence after “Forget Device”

## How to run?

### Option A: Recommended Stateful Orchestrator (Reboot-Safe)

We have created a master orchestration script `run_experiment.sh` that guides you step-by-step through the phases, survives reboots, avoids typos in metadata, and automatically triggers carving, diff comparisons, and MAC address auditing.

Simply run:
```bash
./run_experiment.sh
```

**What it does:**
1. **Phase 0 (Setup & Clean):** Prompts you for the experiment profile (Experiment ID, Device Type, Target MAC, and Friendly Name). It then backs up and wipes all Bluetooth files.
2. **Reboot Intermission:** It instructs you to restart your computer now.
3. **Phase 1 (Post-Reboot Baseline):** Once restarted, run `./run_experiment.sh` again. It verifies the reboot, captures your clean baseline state, and records it in `results.csv`.
4. **Phase 2 (Active Pairing):** Connect your device. Rerun `./run_experiment.sh` to capture the paired configurations and update `results.csv`.
5. **Phase 3 (Forget & Carve):** Click "Forget This Device" in macOS settings. Rerun `./run_experiment.sh` to capture the final state, auto-carve SQLite databases, compare baseline vs forget, scan for MAC remnants, and output reports.

---

### Option B: Running Individual Scripts Manually

If you prefer to run each step manually, use the following sequence:

**Important Arguments:**
* `<dir>` — Directory prefix for state storage (e.g. `baseline_clean`, `after_pair`, `after_forget`).
* `<experiment_id>` — Identifier for the experiment (e.g., `EXP1`).
* `<phase>` — Current experiment phase (`baseline`, `paired`, `after_forget`).
* `<device_type>` — Type of device (e.g. `mouse`, `keyboard`, `headphones`, `speaker`).
* `<mac>` — MAC address of the target device.

#### 1. Clean Baseline (Pre-Reboot Reset & Post-Reboot Collection)
```bash
# A. Wipe and reset (Requires sudo)
sudo ./reset_bt.sh

# [!] REBOOT YOUR COMPUTER HERE [!]

# B. Capture baseline after reboot
./collect_state.sh baseline_clean

# C. Log baseline results (replace timestamp suffix with actual directory)
./log_results.sh baseline_clean_timestamp EXP1 baseline mouse F8:4D:89:4C:79:D7
```

#### 2. Pair and Connect Device Manually
Connect your device in macOS System Settings.

#### 3. Capture Paired State
```bash
# A. Capture paired configuration
./collect_state.sh after_pair

# B. Log paired results (replace timestamp suffix with actual directory)
./log_results.sh after_pair_timestamp EXP1 paired mouse F8:4D:89:4C:79:D7
```

#### 4. Forget Device
Forget the device in macOS System Settings, then toggle Bluetooth OFF/ON.

#### 5. Collect & Analyze Forgotten State
```bash
# A. Capture forgotten configurations
./collect_state.sh after_forget

# B. Run SQLite carving helper (handles directory input dynamically)
./carve_ble.sh after_forget_timestamp

# C. Log forgotten results (replace timestamp suffix with actual directory)
./log_results.sh after_forget_timestamp EXP1 after_forget mouse F8:4D:89:4C:79:D7

# D. Smarter State Diffing (generates comparison_summary.txt & comparison.diff inside folder)
./compare_states.sh baseline_clean_timestamp after_forget_timestamp

# E. Scan for MAC remnants (creates mac_scan_results.txt inside folder)
./scan_for_macs.sh after_forget_timestamp F8:4D:89:4C:79:D7
```


## Scenario ideas:
* Forget immediately after pairing
* Forget after multiple connections
* Forget after reboot
* Forget and reboot
* Forget while device is disconnected

Measure for each artifact, does the device entry:
* disappear completely?
* remain partially (e.g., MAC address)?
* remain in another file but not UI?

## Variables to control

* macOS version
* Hardware:
    * Apple Silicon vs Intel
* Device type:
    * Apple (AirPods, Magic Mouse)
    * BLE (fitness tracker, beacon)
    * Classic BT (keyboard, speaker)
* iCloud state:
    * ON vs OFF
* Connection state:
    * Paired (or has been paired in the past) 
    * New (Never paired)
* Bluetooth type:
    * BLE
    * Classic Bluetooth

## Variables to measure

* Artifact presence (before vs after “Forget Device”)
* Timestamp values across sources
* Residual entries (deleted vs partially removed)
* Cross-device reappearance (iCloud sync)

## Artifact targets

System-level:
* `/Library/Preferences/com.apple.Bluetooth.plist` — Core Bluetooth system preferences.
* `/Library/Bluetooth/` — System Bluetooth directory, containing:
    * `com.apple.MobileBluetooth.devices.plist` (or `/Library/Bluetooth/Library/Preferences/com.apple.MobileBluetooth.devices.plist`) — Device plist.
    * `com.apple.MobileBluetooth.ledevices.paired.db` — SQLite database for paired BLE devices.
* `/private/var/db/blued/` — Lower-level Bluetooth daemon storage (contains link keys, etc.).
* `/private/var/log/` — Legacy logs (e.g., system.log filtering on older macOS).
* Unified logs — Dynamic OS logs captured via `log show` for timing analysis.

User-level (under `~/Library/Preferences/`):
* `ByHost/com.apple.Bluetooth.*.plist` — Host-specific user Bluetooth settings.
* `com.apple.bluetooth.plist` — Core user-level Bluetooth preference file.
* `com.apple.bluetoothuserd.plist` — User Bluetooth daemon preferences.

iCloud-related (under `~/Library/Preferences/`):
* `MobileMeAccounts.plist` — System iCloud account configuration (used to assess cross-device sync state).

