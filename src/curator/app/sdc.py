from typing import Dict, List
from curator.app.image_models import Image
from pywikibot import WbTime, Timestamp, Claim, ItemPage
from curator.app.config import (
    PWB_SITE_COMMONS,
    PWB_SITE_WIKIDATA,
    WikidataEntity,
    WikidataProperty,
)


def build_mapillary_sdc(data: Image) -> List[Dict]:
    """
    Build Structured Data on Commons (SDC) claims for a Mapillary image payload.

    Returns a list of claim JSON objects suitable for MediaInfo editing.
    """
    username = data.creator.username

    claim_creator = Claim(PWB_SITE_COMMONS, WikidataProperty.Creator)
    claim_creator.setSnakType("somevalue")

    author_qualifier = Claim(PWB_SITE_COMMONS, WikidataProperty.AuthorNameString)
    author_qualifier.setTarget(username)
    claim_creator.addQualifier(author_qualifier)

    url_qualifier = Claim(PWB_SITE_COMMONS, WikidataProperty.Url)
    url_qualifier.setTarget(data.creator.profile_url)
    claim_creator.addQualifier(url_qualifier)

    claim_mapillary_id = Claim(PWB_SITE_COMMONS, WikidataProperty.MapillaryPhotoID)
    claim_mapillary_id.setTarget(data.id)

    claim_published_in = Claim(PWB_SITE_COMMONS, WikidataProperty.PublishedIn)
    claim_published_in.setTarget(
        ItemPage(PWB_SITE_WIKIDATA, WikidataEntity.MapillaryDatabase)
    )

    ts = Timestamp.fromISOformat(data.captured_at)
    wbtime = WbTime(ts.year, ts.month, ts.day, precision=WbTime.PRECISION["day"])
    claim_inception = Claim(PWB_SITE_COMMONS, WikidataProperty.Inception)
    claim_inception.setTarget(wbtime)

    claim_source_of_file = Claim(PWB_SITE_COMMONS, WikidataProperty.SourceOfFile)
    claim_source_of_file.setTarget(
        ItemPage(PWB_SITE_WIKIDATA, WikidataEntity.FileAvailableOnInternet)
    )

    operator_qualifier = Claim(PWB_SITE_COMMONS, WikidataProperty.Operator)
    operator_qualifier.setTarget(ItemPage(PWB_SITE_WIKIDATA, WikidataEntity.Mapillary))
    claim_source_of_file.addQualifier(operator_qualifier)

    return [
        claim_creator.toJSON(),
        claim_mapillary_id.toJSON(),
        claim_published_in.toJSON(),
        claim_inception.toJSON(),
        claim_source_of_file.toJSON(),
    ]
