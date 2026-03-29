"""Reverse geocoding functionality for image location enrichment."""

import asyncio
import logging

import httpx

from curator.asyncapi import MediaImage
from curator.core.config import GEOCODING_API_URL, GEOCODING_CONCURRENCY_LIMIT

logger = logging.getLogger(__name__)


async def reverse_geocode(
    latitude: float,
    longitude: float,
    http_client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> dict[str, str | None] | None:
    """Fetch reverse geocoding data for given coordinates."""
    async with semaphore:
        logger.info(f"Fetching geocoding data for {latitude},{longitude}")

        try:
            params = {"lat": latitude, "lon": longitude, "zoom": 18, "format": "jsonv2"}
            response = await http_client.get(
                GEOCODING_API_URL, params=params, timeout=10.0
            )
            response.raise_for_status()

            data = response.json()  # Note: json() is synchronous in httpx
            address = data.get("address", {})

            # Handle both city and town fields from geocoding API
            city = address.get("city") or address.get("town")

            return {
                "city": city,
                "county": address.get("county"),
                "state": address.get("state"),
                "country": address.get("country"),
                "country_code": address.get("country_code"),
                "postcode": address.get("postcode"),
            }
        except (httpx.HTTPError, KeyError, ValueError) as e:
            logger.warning(f"Geocoding failed for {latitude},{longitude}: {e}")
            return None


async def reverse_geocode_batch(
    images: list[MediaImage],
    http_client: httpx.AsyncClient,
) -> None:
    """Fetch reverse geocoding data for a batch of images."""
    semaphore = asyncio.Semaphore(GEOCODING_CONCURRENCY_LIMIT)

    tasks = []
    for image in images:
        if image.location and image.location.latitude and image.location.longitude:
            task = reverse_geocode(
                image.location.latitude,
                image.location.longitude,
                http_client,
                semaphore,
            )
            tasks.append((image, task))

    # Execute all geocoding requests concurrently
    results = await asyncio.gather(*[task for _, task in tasks])

    # Update images with geocoding data
    for (image, _), result in zip(tasks, results):
        if result and image.location:
            # Update existing GeoLocation object with new fields
            image.location.city = result.get("city")
            image.location.county = result.get("county")
            image.location.state = result.get("state")
            image.location.country = result.get("country")
            image.location.country_code = result.get("country_code")
            image.location.postcode = result.get("postcode")
