import requests
import os
import time

def test_download():
    # 1. Create a dummy file in the tmp/test_session directory
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    download_dir = os.path.join(backend_dir, "tmp", "test_session")
    os.makedirs(download_dir, exist_ok=True)
    
    filename = f"test_download_{int(time.time())}.txt"
    file_path = os.path.join(download_dir, filename)
    
    with open(file_path, "w") as f:
        f.write("This is a test file for the download endpoint.")
    
    print(f"Created test file at: {file_path}")
    
    # 2. Try to download it via the BFF
    url = f"http://localhost:8002/api/download/test_session/{filename}"
    print(f"Attempting to download from: {url}")
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            print("Successfully downloaded the file!")
            print(f"Content: {response.text}")
        else:
            print(f"Failed to download. Status code: {response.status_code}")
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error during download request: {e}")

if __name__ == "__main__":
    test_download()
