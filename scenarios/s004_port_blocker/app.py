import os
import time
import requests

def get_qdrant_settings():
    """Get Qdrant connection settings from environment."""
    host = os.getenv("QDRANT_HOST", "qdrant")
    port = os.getenv("QDRANT_PORT", "6333")
    url = os.getenv("QDRANT_URL", f"http://{host}:{port}")
    return {"host": host, "port": port, "url": url}

def wait_for_qdrant(url: str, max_attempts: int = 30, delay: int = 2):
    """Wait for Qdrant to become available."""
    print(f"Waiting for Qdrant at {url}...")
    
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(f"{url}/healthz", timeout=2)
            if response.status_code == 200:
                print(f"✓ Qdrant is ready!")
                return True
        except requests.exceptions.RequestException as e:
            print(f"  Attempt {attempt}/{max_attempts}: {type(e).__name__}")
        
        time.sleep(delay)
    
    print(f"✗ Qdrant did not become available after {max_attempts} attempts")
    return False

def create_test_collection(url: str):
    """Create a test collection in Qdrant."""
    collection_name = "test_collection"
    
    print(f"Creating test collection '{collection_name}'...")
    
    payload = {
        "vectors": {
            "size": 384,
            "distance": "Cosine"
        }
    }
    
    try:
        response = requests.put(
            f"{url}/collections/{collection_name}",
            json=payload,
            timeout=5
        )
        
        if response.status_code == 200:
            print(f"✓ Collection '{collection_name}' created successfully")
            return True
        else:
            print(f"✗ Failed to create collection: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Error creating collection: {e}")
        return False

def main():
    settings = get_qdrant_settings()
    
    print("=" * 50)
    print("RAG Agent - Qdrant Connection Test")
    print("=" * 50)
    print(f"Qdrant URL: {settings['url']}")
    print()
    
    if not wait_for_qdrant(settings["url"]):
        print("\n❌ Failed to connect to Qdrant")
        exit(1)
    
    if create_test_collection(settings["url"]):
        print("\n✓ RAG agent initialized successfully")
        print("Keeping container alive for inspection...")
        
        # Keep container running
        while True:
            time.sleep(60)
    else:
        print("\n❌ Failed to initialize RAG agent")
        exit(1)

if __name__ == "__main__":
    main()
