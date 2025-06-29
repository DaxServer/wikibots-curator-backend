import os
import sys
import requests
import tarfile
import tempfile
import json # Added for parsing GitHub API response

def setup_frontend_assets(repo_owner: str = "DaxServer", repo_name: str = "wikibots-curator-frontend", asset_name: str = "dist.tar.gz", target_dir: str = "frontend"):
    """
    Downloads and extracts frontend assets from a GitHub release.

    Args:
        repo_owner (str): The owner of the GitHub repository.
        repo_name (str): The name of the GitHub repository.
        asset_name (str): The name of the asset to download (e.g., 'dist.tar.gz').
        target_dir (str): The directory where assets should be extracted.
    """
    print(f"Setting up frontend assets from {repo_owner}/{repo_name}...")

    # Step 2: Fetch the latest release information
    api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
    print(f"Fetching release info from: {api_url} (timeout 30s)")
    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()  # Raise an exception for HTTP errors
        print("Successfully fetched release info.")
        release_data = response.json()
        print("Successfully parsed release JSON.")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching release information: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing release information JSON: {e}")
        sys.exit(1)

    # Step 3: Extract the asset download URL
    asset_download_url = None
    for asset in release_data.get("assets", []):
        if asset.get("name") == asset_name:
            asset_download_url = asset.get("browser_download_url")
            break

    if not asset_download_url:
        print(f"Error: Asset '{asset_name}' not found in the latest release.")
        sys.exit(1)

    print(f"Found asset download URL: {asset_download_url}")

    # Step 4: Download the asset
    print(f"Downloading asset from: {asset_download_url} (timeout 60s)...")
    try:
        asset_response = requests.get(asset_download_url, stream=True, timeout=60)
        asset_response.raise_for_status()
        print("Asset download request successful, starting stream...")
    except requests.exceptions.RequestException as e:
        print(f"Error downloading asset: {e}")
        sys.exit(1)

    # Step 5: Create the target directory if it doesn't exist
    try:
        os.makedirs(target_dir, exist_ok=True)
        print(f"Ensured target directory '{target_dir}' exists.")
    except OSError as e:
        print(f"Error creating directory '{target_dir}': {e}")
        sys.exit(1)

    # Step 6: Save and extract the downloaded asset (Revised to use fileobj)
    try:
        print("Preparing to save asset to temporary file...")
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=True) as tmp_file:
            # The path tmp_file.name is available here if needed for logging,
            # but will be invalid after the 'with' block closes.
            print(f"Temporary file object created (will be auto-deleted on close). Path: {tmp_file.name}")
            for chunk_num, chunk in enumerate(asset_response.iter_content(chunk_size=8192)):
                if chunk_num % 10 == 0: # Log every 10 chunks
                    print(f"Writing chunk {chunk_num} to temporary file...")
                tmp_file.write(chunk)

            tmp_file.flush() # Ensure all data is written to disk
            tmp_file.seek(0) # Rewind the file to the beginning for reading by tarfile

            print(f"Asset downloaded to temporary file. Checking if it's a valid tarfile...")
            if not tarfile.is_tarfile(fileobj=tmp_file): # Check using the file object
                tmp_file.seek(0) # Rewind again for debug read
                print(f"Error: Downloaded data is not a valid tarfile.")
                print(f"First 100 bytes of the downloaded data: {tmp_file.read(100)}")
                sys.exit(1)

            tmp_file.seek(0) # Rewind again before extraction
            print(f"Extracting temporary file to '{target_dir}'...")
            with tarfile.open(fileobj=tmp_file, mode="r:gz") as tar: # Use the file object directly
                tar.extractall(path=target_dir)
            print("Asset extracted successfully.")
            # tmp_file is automatically deleted when this 'with' block exits

    except tarfile.TarError as e:
        print(f"Error extracting tarfile: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred during file handling: {e}")
        sys.exit(1)
    # No 'finally' block is needed for tmp_file deletion due to delete=True being used with fileobj.

    print("Frontend assets setup complete.")
