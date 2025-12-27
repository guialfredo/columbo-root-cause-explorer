import os
import time
import yaml
import requests

def load_yaml_config(path: str) -> dict:
    """Load YAML configuration file"""
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def effective_qdrant_settings():
    """
    Determine effective Qdrant connection settings.
    BUG: Runtime config file overrides environment variables!
    """
    # 1) Start from environment (what Compose injects)
    host = os.getenv("QDRANT_HOST", "qdrant")
    port = os.getenv("QDRANT_PORT", "6333")

    # 2) Subtle override: runtime config file wins over env
    # This is the source of the bug - the config file contains 'localhost'
    # which doesn't work inside the container
    config_path = os.getenv("APP_CONFIG_PATH")
    cfg = load_yaml_config(config_path)
    qcfg = (cfg.get("qdrant") or {})

    # BUG: These lines override the correct values from environment
    host = qcfg.get("host", host)
    port = str(qcfg.get("port", port))

    url = f"http://{host}:{port}"
    return host, port, url, config_path

host, port, url, config_path = effective_qdrant_settings()

print("=" * 60)
print("RAG Agent Starting...")
print("=" * 60)
print("Effective configuration (after runtime config merge):")
print(f"  APP_CONFIG_PATH={config_path}")
print(f"  QDRANT_HOST={host}")
print(f"  QDRANT_PORT={port}")
print(f"  QDRANT_URL={url}")
print("=" * 60)

# Attempt to connect to Qdrant
for i in range(20):
    try:
        print(f"[Attempt {i+1}/20] Connecting to {url}/healthz...")
        r = requests.get(f"{url}/healthz", timeout=2)
        print(f"  Response: {r.status_code} - {r.text}")
        r.raise_for_status()
        print("✓ Connected to Qdrant successfully!")
        break
    except requests.exceptions.ConnectionError as e:
        print(f"  ✗ Connection failed: {e}")
        time.sleep(1)
    except Exception as e:
        print(f"  ✗ Error: {e}")
        time.sleep(1)
else:
    print("=" * 60)
    print("ERROR: Could not connect to Qdrant after 20 attempts")
    print("=" * 60)
    raise SystemExit("Could not connect to Qdrant")
