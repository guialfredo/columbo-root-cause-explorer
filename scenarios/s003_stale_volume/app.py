from pathlib import Path
import sys

print("=" * 50)
print("Application Startup - Data Validation")
print("=" * 50)

EXPECTED_SCHEMA_VERSION = "2"
SCHEMA_FILE_PATH = Path("/data/schema_version.txt")

print(f"Validating persistent data compatibility...")
print(f"Data location: {SCHEMA_FILE_PATH}")

if not SCHEMA_FILE_PATH.exists():
    print("No existing schema version found. Initializing fresh data store.")
    SCHEMA_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_FILE_PATH.write_text(EXPECTED_SCHEMA_VERSION)
    print(f"Initialized with schema version: {EXPECTED_SCHEMA_VERSION}")
    print("Application ready.")
    sys.exit(0)

found_version = SCHEMA_FILE_PATH.read_text().strip()

if found_version != EXPECTED_SCHEMA_VERSION:
    print("\n" + "!" * 50)
    print("FATAL: Schema version mismatch!")
    print("!" * 50)
    print(f"Expected schema version: {EXPECTED_SCHEMA_VERSION}")
    sys.exit(1)

print("Schema validation passed.")
print("Application ready.")
