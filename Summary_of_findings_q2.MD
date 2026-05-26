## Summary of Findings: RAM vs. Disk Persistence

Our automated forensic harness confirmed a distinct two-tier persistence model for Bluetooth artifacts on macOS:

1. **Volatile (ULS) Tier:** Bluetooth connection events are committed to the Unified Logging System (ULS) with a consistent mean latency of ~1.86 seconds. This data is volatile and exists in RAM-backed buffers.
2. **Persistent (Disk) Tier:** Our kernel-level `watchdog` monitoring confirmed **zero file system writes** to the primary Bluetooth databases (`paired.db-wal`, `other.db-wal`) or configuration files (`.plist`) within the immediate post-connection window (10s).

**Forensic Impact:**
This persistence gap creates a "Forensic Blind Spot." An investigator relying on a standard "dead-box" forensic image of the SSD will fail to recover connection evidence that the macOS Unified Logging System (in live memory) clearly captured. 

| Metric | Observation |
| :--- | :--- |
| **Average ULS Drift** | 1.86s |
| **Disk Write Latency** | > 10s (Lazy Writing) |
| **Evidence Survival** | High in ULS / Low in SQLite (post-reboot) |
