# RQ3 — macOS Bluetooth Artifact Forensics: iCloud Sync Investigation

**Stockholm University — CYFO Project**  
**Research Question 3:** Does iCloud sync propagate Bluetooth pairing data across devices after a Forget Device operation on macOS?

---

## Overview

This repository documents the forensic investigation of Bluetooth artifact storage and iCloud synchronisation behaviour on macOS 26 (Tahoe). The experiment was conducted on 2026-05-27 using a Mac mini running macOS 26.4.1 (Build 25E253), accessed remotely via RealVNC and SSH, with a fresh Apple ID.

---

## Repository Structure

```
├── scripts/
│   ├── 01_baseline_collection.sh     # Capture pre-experiment artifact state
│   ├── 02_artifact_discovery.sh      # Locate BT artifacts on macOS 26
│   ├── 03_post_forget_snapshot.sh    # Capture state immediately after Forget Device
│   └── 04_cloudkit_log_analysis.sh   # Analyse CloudKit Bluetooth activity
├── artifacts/
│   ├── mobilebluetooth_pre_forget_hash.txt
│   ├── mobilebluetooth_post_forget_hash.txt
│   └── cloudkit_bt_summary.txt
├── findings/
│   └── RQ3_Session_Notes.docx        # Full session notes and findings
└── notes/
    └── methodology.md                # Procedure, limitations, next steps
```

---

## Key Findings

### 1. Primary Artifact Location Has Changed in macOS 26

Prior forensic literature and tools referencing these locations will find nothing on macOS 26:
- `~/Library/Bluetooth/`
- `/Library/Preferences/com.apple.Bluetooth.plist`

The actual primary Bluetooth pairing database on macOS 26 is:
```
/Library/Bluetooth/Library/Preferences/com.apple.MobileBluetooth.devices.plist
```
This file is SIP-protected and cannot be accessed via `sudo ls` or `sudo shasum` on a standard macOS 26 installation. Reading requires specific entitlements (`plutil`, `defaults`, `PlistBuddy`).

---

### 2. Forget Device Leaves a MAC Address Tombstone

Performing Forget Device via System Settings does **not** delete the device record from `com.apple.MobileBluetooth.devices.plist`. The entry is reduced to a minimal stub:

```xml
<key>F8:4D:89:4C:79:D7</key>
<dict>
    <key>AACPCapabilitiesIntegersLength</key>
    <integer>0</integer>
    <key>AACPCapabilitiesLength</key>
    <integer>0</integer>
</dict>
```

The device MAC address persists as a key. A forensic examiner would find the device identifier in the plist after a user-initiated Forget Device operation.

**Hash evidence:**
| State | SHA-256 |
|---|---|
| Pre-forget | `a2181c76bc07d4b0166126c6c6c7be031b35c7db4f3586bc886076d2ed69a8d7` |
| Post-forget | `12e967613027d9529b6d82edff2353acc78edb3741587554509f6026ca0f6e79` |

---

### 3. Previous Owner Identity Persists Across Account Changes

The `UserNameKey` field in paired AirPods entries retained the previous user's name after a fresh Apple ID was signed in:

```
UserNameKey = "Kadri's AirPods Pro"
UserNameKey = "Kadri's AirPods"
```

PII from a prior user is not cleared from local Bluetooth artifacts when a new Apple ID is signed in.

---

### 4. IRK Hashes Present in HID Device Records

Magic Keyboard and Magic Mouse entries contain `DevicePrimaryHash` and `DeviceSecondaryHash` fields — SHA-1 hashes of the BLE Identity Resolving Key (IRK):

```
Keyboard DevicePrimaryHash:   0x0cadbb065fbeb441cbe99fbf2f9e98e398b44be3
Mouse    DevicePrimaryHash:   0xc5c488248cc54e9ecc750b314071c6280db59426
```

If these propagate via iCloud, a recipient device could resolve randomised private BLE MAC addresses back to the physical device without re-pairing. This is the primary security concern for RQ3.

---

### 5. Three Dedicated Bluetooth CloudKit Containers Confirmed

System log analysis of `audioaccessoryd` revealed three dedicated CloudKit containers in the Production environment:

| Container | Likely Purpose |
|---|---|
| `com.apple.bluetooth` | General BT device metadata |
| `com.apple.bluetooth.services` | BT service records |
| `com.apple.securedBluetooth` | Cryptographic pairing material (LTKs/IRKs) |

The `com.apple.securedBluetooth` container is the most forensically significant — its name suggests it handles the sensitive cryptographic keys absent from the main devices plist.

---

### 6. Fresh Apple ID Cannot Complete Bluetooth CloudKit Sync

All three containers returned `persona: (null)` for the fresh Apple ID. The `audioaccessoryd` process entered a crash loop (new PID spawned every ~10 seconds) as it repeatedly failed the CloudKit subscription handshake. `~/Library/SyncedPreferences/` remained empty throughout.

**Implication:** The iCloud sync pathway for Bluetooth data **exists and is active** on macOS 26, but requires an established Apple ID with prior device history to authenticate. A fresh account cannot trigger sync.

---

## Structural Difference Between Device Types

| Field | AirPods | Magic Keyboard/Mouse |
|---|---|---|
| `DevicePrimaryHash` (IRK) | Absent | Present |
| `DeviceSecondaryHash` | Absent | Present |
| `UserNameKey` | Present (owner name) | Absent |
| `SdpCache` | Absent | Present |
| Pairing mechanism | W1/H1 chip (iCloud-mediated) | Standard BLE bonding |

AirPods use Apple's proprietary W1/H1 chip pairing which is iCloud-mediated by design. Their credentials are not stored in the local devices plist. HID devices use standard BLE bonding and store IRK hashes locally.

---

## Usage

All scripts require macOS and should be run with appropriate permissions:

```bash
chmod +x scripts/*.sh

# Run in order:
./scripts/01_baseline_collection.sh   # Before any experiment actions
./scripts/02_artifact_discovery.sh    # To locate artifacts on macOS 26
# [Perform Forget Device via System Settings]
./scripts/03_post_forget_snapshot.sh  # Immediately after Forget Device
./scripts/04_cloudkit_log_analysis.sh # At any point to analyse CloudKit
```

---

## Open Questions / Next Session

- Does `com.apple.securedBluetooth` propagate IRK hashes on an **established** Apple ID?
- Is the tombstone MAC address eventually purged, or does it persist indefinitely?
- Does the Forget Device tombstone appear on a second device signed into the same Apple ID via CloudKit?
- Are LTKs stored in the Secure Enclave, keychain, or the `com.apple.securedBluetooth` container?

See `notes/methodology.md` for full next session requirements.

---

## Limitations

- Experiment conducted remotely (RealVNC + SSH) — no physical device pairing performed
- Fresh Apple ID blocked CloudKit sync — core RQ3 propagation question unanswered
- SIP on macOS 26 restricts direct forensic access to `/Library/Bluetooth/`
- Pre-existing paired devices used (previous user "Kadri") rather than freshly paired device

---

## References

- macOS 26.4.1 (Build 25E253) — tested 2026-05-27
- CloudKit containers identified via `log show` analysis of `audioaccessoryd`
- Artifact location confirmed via `fs_usage` and `mdfind`
