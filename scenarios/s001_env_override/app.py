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
    cfg = load_yaml_config(config_path or "")
    qcfg = (cfg.get("qdrant") or {})

    # BUG: These lines override the correct values from environment
    host = qcfg.get("host", host)
    port = str(qcfg.get("port", port))

    url = f"http://{host}:{port}"
    return host, port, url, config_path

host, port, url, config_path = effective_qdrant_settings()

print("RAG Agent starting...")

# Attempt to connect to Qdrant
for i in range(20):
    try:
        r = requests.get(f"{url}/healthz", timeout=2)
        r.raise_for_status()
        print("✓ Connected to Qdrant successfully!")
        break
    except requests.exceptions.ConnectionError:
        # Suppress detailed connection errors
        time.sleep(1)
    except Exception:
        # Suppress other errors
        time.sleep(1)
else:
    print("ERROR: Failed to connect to Qdrant vector database")
    raise SystemExit(1)
