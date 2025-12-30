import json
import time
import os
from pathlib import Path

CONFIG_PATH = Path("/data/config/settings.json")
CHECKPOINT_DIR = Path("/data/checkpoints")

def load_config():
    """Load config from volume."""
    print(f"Loading config from {CONFIG_PATH}...")
    
    if not CONFIG_PATH.exists():
        print(f"✗ Config file not found: {CONFIG_PATH}")
        exit(1)
    
    try:
        config = json.loads(CONFIG_PATH.read_text())
        print(f"✓ Config loaded:  {config}")
        return config
    except PermissionError as e:
        print(f"✗ Permission denied reading config: {e}")
        exit(1)

def save_checkpoint(batch_num:  int):
    """Save checkpoint to volume."""
    checkpoint_file = CHECKPOINT_DIR / f"checkpoint_{batch_num}.json"
    
    print(f"Saving checkpoint to {checkpoint_file}...")
    
    try:
        checkpoint_data = {
            "batch":  batch_num,
            "timestamp": time.time(),
            "status": "completed"
        }
        
        checkpoint_file.write_text(json.dumps(checkpoint_data, indent=2))
        print(f"✓ Checkpoint saved")
        return True
        
    except Exception as e:
        print(f"✗ Failed to save checkpoint: {e}")
        return False

def main():
    print("=" * 60)
    print("Data Processing Worker Starting...")
    print("=" * 60)
    
    # Load config (this will work - file is world-readable)
    config = load_config()
    print("✓ Pipeline initialized successfully\n")
    
    # Simulate processing batches
    batch_size = config. get("batch_size", 100)
    checkpoint_interval = config.get("checkpoint_interval", 10)
    
    for batch_num in range(1, 4):
        print(f"Processing batch {batch_num} ({batch_size} items)...")
        time.sleep(2)  # Simulate processing
        
        # Try to save checkpoint (this will fail - directory not writable)
        if not save_checkpoint(batch_num):
            print(f"\n{'!' * 60}")
            print("FATAL: Cannot save checkpoint - aborting pipeline")
            print("Checkpoint persistence is required for data integrity")
            print("!" * 60)
            exit(1)
        
        print(f"Batch {batch_num} complete\n")
    
    print("✓ All batches processed successfully")

if __name__ == "__main__":
    main()