## A script to test delay between real time connection of a device and database timestamp
import subprocess
import time
from datetime import datetime, timezone

def get_boot_time():
    result = subprocess.check_output(['sysctl', '-n', 'kern.boottime']).decode()
    # Extract seconds from "{ sec = XXXXXXXXXX, usec = XXXXXX } ..."
    sec = int(result.split('sec = ')[1].split(',')[0].strip())
    return sec

def ms_since_boot_to_wallclock(ms, boot_time):
    wall = boot_time + ms / 1000
    return datetime.fromtimestamp(wall, tz=timezone.utc).astimezone()

def query_db():
    result = subprocess.check_output([
        'sudo', 'sqlite3',
        '/Library/Bluetooth/com.apple.MobileBluetooth.ledevices.paired.db',
        'SELECT Name, LastSeenTime, LastConnectionTime FROM PairedDevices;'
    ]).decode()
    return result.strip().split('\n')

def parse_row(row):
    parts = row.split('|')
    return {
        'name': parts[0],
        'last_seen_ms': int(parts[1]),
        'last_connection_ms': int(parts[2])
    }

print("=" * 60)
print("STEP 1: Waiting for you to connect a Bluetooth device...")
print("Press ENTER the moment you turn on / connect the device.")
print("=" * 60)
input()

# Capture wall clock immediately
wall_clock_event = datetime.now(tz=timezone.utc).astimezone()
print(f"\n✓ Event recorded at: {wall_clock_event}")

# Small delay to let macOS write to DB
print("Waiting 3 seconds for macOS to update the database...")
time.sleep(3)

boot_time = get_boot_time()
print(f"✓ Boot time (Unix): {boot_time}")

print("\nQuerying database...")
rows = query_db()

print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)
for row in rows:
    if not row:
        continue
    d = parse_row(row)
    last_seen_wall = ms_since_boot_to_wallclock(d['last_seen_ms'], boot_time)
    last_conn_wall = ms_since_boot_to_wallclock(d['last_connection_ms'], boot_time)
    
    print(f"\nDevice:              {d['name']}")
    print(f"LastSeenTime (ms):   {d['last_seen_ms']} -> {last_seen_wall}")
    print(f"LastConnTime (ms):   {d['last_connection_ms']} -> {last_conn_wall}")

print("\n" + "=" * 60)
print(f"Your recorded event time: {wall_clock_event}")
print("Compare above to find the matching device and measure delay.")
print("=" * 60)
```
