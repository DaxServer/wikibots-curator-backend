from curator.app.wcqs import WcqsSession
from pywikibot import WbQuantity
from datetime import datetime
from functools import lru_cache
from typing import Any, Dict, List
from fastapi import Request

from curator.app.config import (
    MAPILLARY_API_TOKEN,
    PWB_SITE_COMMONS,
    PWB_SITE_WIKIDATA,
    WikidataEntity,
    WikidataProperty,
)
from curator.app.image_models import Creator, Image, Location, Dates, ExistingPage
from curator.app.ingest.interfaces import Handler
import httpx
from pywikibot import Claim, ItemPage, Timestamp, WbTime


def from_mapillary(image: Dict[str, Any]) -> Image:
    coords = image.get("geometry").get("coordinates")
    owner = image.get("creator")
    creator = Creator(
        id=str(owner.get("id")),
        username=owner.get("username"),
        profile_url=f"https://www.mapillary.com/app/user/{owner.get('username')}",
    )
    loc = Location(
        latitude=coords[1],
        longitude=coords[0],
        compass_angle=image.get("compass_angle"),
    )
    dt = datetime.fromtimestamp(image.get("captured_at") / 1000.0)
    date = dt.date().isoformat()
    return Image(
        id=str(image.get("id")),
        title=f"Photo from Mapillary {date} ({str(image.get('id'))}).jpg",
        dates=Dates(taken=dt),
        creator=creator,
        location=loc,
        url_original=image.get("thumb_original_url"),
        url=f"https://www.mapillary.com/app/?pKey={image.get('id')}&focus=photo",
        thumbnail_url=image.get("thumb_256_url"),
        preview_url=image.get("thumb_1024_url"),
        width=image.get("width"),
        height=image.get("height"),
        camera_make=image.get("make"),
        camera_model=image.get("model"),
        is_pano=image.get("is_pano"),
    )


@lru_cache(maxsize=128)
def _fetch_sequence_data(sequence_id: str) -> dict:
    """
    Fetch sequence data from Mapillary API
    """
    response = httpx.get(
        f"https://graph.mapillary.com/images",
        params={
            "access_token": MAPILLARY_API_TOKEN,
            "sequence_ids": sequence_id,
            "fields": "captured_at,compass_angle,creator,geometry,height,is_pano,make,model,thumb_256_url,thumb_1024_url,thumb_original_url,width",
        },
        timeout=30,
    )
    response.raise_for_status()
    images = response.json()["data"]

    # sort by captured_at
    images.sort(key=lambda x: x["captured_at"])

    return {str(i["id"]): i for i in images}


class MapillaryHandler(Handler):
    name = "mapillary"

    def fetch_collection(self, input: str) -> Dict[str, Image]:
        source = _fetch_sequence_data(input)
        return {k: from_mapillary(v) for k, v in source.items()}

    def fetch_image_metadata(self, image_id: str, input: str) -> Image:
        collection = self.fetch_collection(input)
        image = collection.get(image_id)
        if not image:
            raise ValueError(
                f"Image data not found in sequence for image_id={image_id}"
            )
        return image

    def fetch_existing_pages(
        self, image_ids: List[str], request: Request
    ) -> Dict[str, List[ExistingPage]]:
        """
        Fetch existing Wikimedia Commons pages for the given Mapillary image IDs.

        Queries WCQS to find files that have already been uploaded with these Mapillary IDs
        to prevent duplicate uploads.
        """
        query = f"""
            SELECT ?file ?id WHERE {{
              VALUES ?id {{ { " ".join([f'"{i}"' for i in image_ids]) } }}
              ?file wdt:{WikidataProperty.MapillaryPhotoID} ?id.
            }}
            """

        results = WcqsSession(request).query(query)

        existing_pages = {}
        for r in results["results"]["bindings"]:
            image_id = r["id"]["value"]
            file_url = r["file"]["value"]
            if image_id not in existing_pages:
                existing_pages[image_id] = []
            existing_pages[image_id].append(ExistingPage(url=file_url))

        return existing_pages

    def build_sdc(self, image: Image) -> List[Dict]:
        """
        Build Structured Data on Commons (SDC) claims for a Mapillary image payload.

        Returns a list of claim JSON objects suitable for MediaInfo editing.
        """
        username = image.creator.username

        claim_creator = Claim(PWB_SITE_COMMONS, WikidataProperty.Creator)
        claim_creator.setSnakType("somevalue")

        author_qualifier = Claim(PWB_SITE_COMMONS, WikidataProperty.AuthorNameString)
        author_qualifier.setTarget(username)
        claim_creator.addQualifier(author_qualifier)

        url_qualifier = Claim(PWB_SITE_COMMONS, WikidataProperty.Url)
        url_qualifier.setTarget(image.creator.profile_url)
        claim_creator.addQualifier(url_qualifier)

        claim_mapillary_id = Claim(PWB_SITE_COMMONS, WikidataProperty.MapillaryPhotoID)
        claim_mapillary_id.setTarget(image.id)

        claim_published_in = Claim(PWB_SITE_COMMONS, WikidataProperty.PublishedIn)
        claim_published_in.setTarget(
            ItemPage(PWB_SITE_WIKIDATA, WikidataEntity.MapillaryDatabase)
        )

        ts = Timestamp.fromISOformat(image.dates.taken.isoformat())
        wbtime = WbTime(ts.year, ts.month, ts.day, precision=WbTime.PRECISION["day"])
        claim_inception = Claim(PWB_SITE_COMMONS, WikidataProperty.Inception)
        claim_inception.setTarget(wbtime)

        claim_source_of_file = Claim(PWB_SITE_COMMONS, WikidataProperty.SourceOfFile)
        claim_source_of_file.setTarget(
            ItemPage(PWB_SITE_WIKIDATA, WikidataEntity.FileAvailableOnInternet)
        )

        operator_qualifier = Claim(PWB_SITE_COMMONS, WikidataProperty.Operator)
        operator_qualifier.setTarget(
            ItemPage(PWB_SITE_WIKIDATA, WikidataEntity.Mapillary)
        )
        claim_source_of_file.addQualifier(operator_qualifier)

        described_at_url_qualifier = Claim(
            PWB_SITE_COMMONS, WikidataProperty.DescribedAtUrl
        )
        described_at_url_qualifier.setTarget(image.url)
        claim_source_of_file.addQualifier(described_at_url_qualifier)

        copyright_claim = Claim(PWB_SITE_COMMONS, WikidataProperty.CopyrightStatus)
        copyright_claim.setTarget(
            ItemPage(PWB_SITE_WIKIDATA, WikidataEntity.Copyrighted)
        )

        copyright_license_claim = Claim(
            PWB_SITE_COMMONS, WikidataProperty.CopyrightLicense
        )
        copyright_license_claim.setTarget(
            ItemPage(PWB_SITE_WIKIDATA, WikidataEntity.CCBYSA40)
        )

        width_claim = Claim(PWB_SITE_COMMONS, WikidataProperty.Width)
        width_claim.setTarget(
            WbQuantity(image.width, ItemPage(PWB_SITE_WIKIDATA, WikidataEntity.Pixel))
        )

        height_claim = Claim(PWB_SITE_COMMONS, WikidataProperty.Height)
        height_claim.setTarget(
            WbQuantity(image.height, ItemPage(PWB_SITE_WIKIDATA, WikidataEntity.Pixel))
        )

        return [
            claim_creator.toJSON(),
            claim_mapillary_id.toJSON(),
            claim_published_in.toJSON(),
            claim_inception.toJSON(),
            claim_source_of_file.toJSON(),
            copyright_claim.toJSON(),
            copyright_license_claim.toJSON(),
            width_claim.toJSON(),
            height_claim.toJSON(),
        ]
