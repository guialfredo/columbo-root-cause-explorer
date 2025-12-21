import os
import time
import yaml
import requests

def load_yaml_config(path: str) -> dict:
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def effective_qdrant_settings():
    # 1) Start from environment (what Compose injects)
    host = os.getenv("QDRANT_HOST", "qdrant")
    port = os.getenv("QDRANT_PORT", "6333")

    # 2) Subtle override: runtime config file wins over env
    config_path = os.getenv("APP_CONFIG_PATH")
    cfg = load_yaml_config(config_path)
    qcfg = (cfg.get("qdrant") or {})

    host = qcfg.get("host", host)
    port = str(qcfg.get("port", port))

    url = f"http://{host}:{port}"
    return host, port, url, config_path

host, port, url, config_path = effective_qdrant_settings()

print("Effective configuration (after runtime config merge):")
print(f"  APP_CONFIG_PATH={config_path}")
print(f"  QDRANT_HOST={host}")
print(f"  QDRANT_PORT={port}")
print(f"  QDRANT_URL={url}")

for i in range(20):
    try:
        r = requests.get(f"{url}/healthz", timeout=2)
        print("Qdrant health:", r.status_code, r.text)
        r.raise_for_status()
        print("Connected to Qdrant successfully.")
        break
    except Exception as e:
        print(f"[{i+1}/20] Connection failed: {e}")
        time.sleep(1)
else:
    raise SystemExit("Could not connect to Qdrant")
