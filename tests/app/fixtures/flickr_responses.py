"""
Flickr API fixtures for testing
"""

import json
from pathlib import Path

# Load the real Flickr API response
FIXTURES_DIR = Path(__file__).parent
with open(FIXTURES_DIR / "flickr_api_response.json") as f:
    FLICKR_API_RESPONSE = json.load(f)

# Real Flickr API response for album page (first 100 photos from page 1)
FLICKR_ALBUM_PAGE_RESPONSE = FLICKR_API_RESPONSE

# Individual photo from the real response (first photo)
FLICKR_PHOTO_WITHOUT_GEO = FLICKR_API_RESPONSE["photoset"]["photo"][0]
