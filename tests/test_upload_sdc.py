import json
from pathlib import Path

from curator.app.sdc_v2 import build_statements_from_mapillary_image
from curator.asyncapi import Creator, Dates, GeoLocation, MediaImage


def _load_sdc_claim_fixtures():
    path = Path(__file__).resolve().parent / "fixtures" / "sdc_claims.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_build_statements_from_mapillary_image_matches_v1_fixtures():
    fixtures = _load_sdc_claim_fixtures()
    for fixture in fixtures:
        sdc_v2 = fixture["sdc_v2"]
        image = MediaImage(
            id=sdc_v2["mapillary_image_id"],
            title=f"Photo from Mapillary ({sdc_v2['mapillary_image_id']}).jpg",
            dates=Dates(taken=sdc_v2["taken_at"]),
            creator=Creator(
                id=sdc_v2["creator_username"],
                username=sdc_v2["creator_username"],
                profile_url=f"https://www.mapillary.com/app/user/{sdc_v2['creator_username']}",
            ),
            location=GeoLocation.model_validate(sdc_v2["location"]),
            url=sdc_v2["source_url"],
            url_original=sdc_v2["source_url"],
            thumbnail_url=sdc_v2["source_url"],
            preview_url=sdc_v2["source_url"],
            width=sdc_v2["width"],
            height=sdc_v2["height"],
            existing=[],
        )
        statements = build_statements_from_mapillary_image(
            image=image,
            include_default_copyright=sdc_v2["include_default_copyright"],
        )
        dumped = [
            s.model_dump(mode="json", by_alias=True, exclude_none=True)
            for s in statements
        ]
        assert dumped == fixture["claims"]
