import os
import sys
import requests
import tarfile
import json
from tempfile import NamedTemporaryFile


frontend_dir = os.path.join(os.path.dirname(__file__), '../..', 'frontend')


def setup_frontend_assets():
    api_url = "https://api.github.com/repos/DaxServer/wikibots-curator-frontend/releases/latest"
    try:
        response = requests.get(api_url, timeout=30, headers={
            "Authorization": f"Bearer {os.environ['GITHUB_PERSONAL_ACCESS_TOKEN']}"
        })
        response.raise_for_status()
        release_data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching release information: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing release information JSON: {e}")
        sys.exit(1)

    asset_download_url = None
    for asset in release_data.get("assets", []):
        if asset.get("name") == 'dist.tar.gz':
            asset_download_url = asset.get("browser_download_url")
            break

    if not asset_download_url:
        print("Error: Asset 'dist.tar.gz' not found in the latest release.")
        sys.exit(1)

    print(f"Found asset download URL: {asset_download_url}")

    try:
        asset_response = requests.get(asset_download_url, stream=True, timeout=60)
        asset_response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error downloading asset: {e}")
        sys.exit(1)

    try:
        os.makedirs(frontend_dir, exist_ok=True)
    except OSError as e:
        print(f"Error creating directory '{frontend_dir}': {e}")
        sys.exit(1)

    try:
        with NamedTemporaryFile(suffix=".tar.gz") as tmp_file:
            for chunk in asset_response.iter_content(chunk_size=8192):
                tmp_file.write(chunk)

            tmp_file.flush()  # Ensure all data is written to disk
            tmp_file.seek(0)  # Rewind the file to the beginning for reading by tarfile

            if not tarfile.is_tarfile(tmp_file.name):
                tmp_file.seek(0)  # Rewind again for debug read
                print("Error: Downloaded data is not a valid tarfile.")
                print(f"First 100 bytes of the downloaded data: {tmp_file.read(100)}")
                sys.exit(1)

            tmp_file.seek(0)  # Rewind again before extraction
            with tarfile.open(fileobj=tmp_file, mode="r:gz") as tar:  # Use the file object directly
                tar.extractall(path=frontend_dir)
            print("Assets extracted successfully.")

    except tarfile.TarError as e:
        print(f"Error extracting tarfile: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during file handling: {e}")
        sys.exit(1)
