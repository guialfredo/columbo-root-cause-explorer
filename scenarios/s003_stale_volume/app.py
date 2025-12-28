from pathlib import Path
import sys

EXPECTED = "2"
p = Path("/data/schema_version.txt")

if not p.exists():
    print("No schema version found. Initializing schema_version=2")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(EXPECTED)
    print("OK")
    sys.exit(0)

found = p.read_text().strip()
if found != EXPECTED:
    print(f"FATAL: incompatible persistent state in volume: schema_version={found}, expected={EXPECTED}")
    print("Hint: you may need to migrate data or reset the volume.")
    sys.exit(1)

print("OK")
