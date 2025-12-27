import os
import time
import requests

def main():
    """
    Service that connects to an external API endpoint.
    The API endpoint URL is BAKED INTO THE IMAGE at build time.
    """
    # This value was set at IMAGE BUILD TIME via ARG -> ENV
    api_endpoint = os.getenv("API_ENDPOINT", "http://api.old-domain.com/health")
    
    print("=" * 60)
    print("API Client Service Starting...")
    print("=" * 60)
    print(f"API_ENDPOINT (from build): {api_endpoint}")
    print("=" * 60)
    
    # Attempt to connect to the API
    for attempt in range(20):
        try:
            print(f"\n[Attempt {attempt + 1}/20] Connecting to {api_endpoint}...")
            response = requests.get(api_endpoint, timeout=5)
            
            if response.status_code == 200:
                print(f"✓ SUCCESS! Connected to {api_endpoint}")
                print(f"Response: {response.text}")
                print("\nService running successfully. Keeping container alive...")
                # Keep container running
                while True:
                    time.sleep(60)
            else:
                print(f"✗ HTTP {response.status_code}: {response.text}")
                
        except requests.exceptions.ConnectionError as e:
            print(f"✗ Connection failed: Cannot reach {api_endpoint}")
            print(f"   Error: {e}")
        except requests.exceptions.Timeout:
            print(f"✗ Connection timeout to {api_endpoint}")
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
        
        if attempt < 19:
            print("Retrying in 3 seconds...")
            time.sleep(3)
    
    print("\n" + "=" * 60)
    print("ERROR: All connection attempts failed!")
    print(f"Could not connect to {api_endpoint}")
    print("=" * 60)
    exit(1)

if __name__ == "__main__":
    main()
