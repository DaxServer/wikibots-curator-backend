from datetime import datetime

from curator.app.image_models import Creator, Dates, ExistingPage, Image, Location


def test_image_serialization():
    creator = Creator(id="u1", username="user1", profile_url="http://example.com/u1")
    dates = Dates(taken=datetime(2023, 1, 1, 12, 0, 0))
    location = Location(latitude=10.0, longitude=20.0)
    existing = [ExistingPage(url="http://commons.wikimedia.org/wiki/File:Test.jpg")]

    image = Image(
        id="img1",
        title="Test Image",
        dates=dates,
        creator=creator,
        location=location,
        url_original="http://example.com/orig.jpg",
        thumbnail_url="http://example.com/thumb.jpg",
        preview_url="http://example.com/preview.jpg",
        url="http://example.com/page",
        width=1000,
        height=800,
        existing=existing,
    )

    dumped = image.model_dump(mode="json")

    assert dumped["id"] == "img1"
    assert dumped["creator"]["username"] == "user1"
    assert dumped["dates"]["taken"] == "2023-01-01T12:00:00"
    assert dumped["location"]["latitude"] == 10.0
    assert (
        dumped["existing"][0]["url"]
        == "http://commons.wikimedia.org/wiki/File:Test.jpg"
    )
    assert isinstance(dumped["existing"], list)
    assert isinstance(dumped["existing"][0], dict)
