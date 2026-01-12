"""BDD tests for mapillary_handler.feature"""

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from curator.handlers.mapillary_handler import from_mapillary

# --- Scenarios ---


@scenario("features/mapillary_handler.feature", 'Mapillary sends "none" as camera make')
def test_mapillary_none_as_camera_make():
    pass


@scenario(
    "features/mapillary_handler.feature", 'Mapillary sends "none" as camera model'
)
def test_mapillary_none_as_camera_model():
    pass


@scenario(
    "features/mapillary_handler.feature", "Mapillary sends valid camera make and model"
)
def test_mapillary_valid_camera_make_and_model():
    pass


@scenario(
    "features/mapillary_handler.feature",
    "Mapillary sends missing camera make and model",
)
def test_mapillary_missing_camera_make_and_model():
    pass


@scenario(
    "features/mapillary_handler.feature",
    'Mapillary sends "none" for both camera make and model',
)
def test_mapillary_none_for_both_camera_make_and_model():
    pass


# --- GIVENS ---


@pytest.fixture
def mapillary_response():
    return {
        "id": "123",
        "geometry": {"coordinates": [10, 20]},
        "creator": {"id": "u1", "username": "user1"},
        "captured_at": 1600000000000,
        "compass_angle": 180,
        "thumb_original_url": "http://original",
        "thumb_256_url": "http://thumb",
        "thumb_1024_url": "http://preview",
        "width": 100,
        "height": 100,
        "is_pano": False,
    }


@given(
    parsers.parse('the Mapillary API response has make="{make}" and model="{model}"')
)
def step_given_mapillary_response_with_make_model(
    make, model, mapillary_response, session_context
):
    # Parse the string values - remove quotes from the parsed values
    make_value = make.strip('"') if make != "null" else None
    model_value = model.strip('"') if model != "null" else None

    mapillary_response["make"] = make_value
    mapillary_response["model"] = model_value

    session_context["mapillary_response"] = mapillary_response


@given("the Mapillary API response has missing make and model")
def step_given_mapillary_response_missing_make_model(
    mapillary_response, session_context
):
    mapillary_response["make"] = None
    mapillary_response["model"] = None
    session_context["mapillary_response"] = mapillary_response


# --- WHENS ---


@when("I convert the response using from_mapillary")
def step_when_convert_from_mapillary(session_context):
    response = session_context["mapillary_response"]
    result = from_mapillary(response)
    session_context["media_image"] = result


# --- THENS ---


@then(parsers.parse("the MediaImage camera_make should be {expected}"))
def step_then_camera_make(session_context, expected):
    media_image = session_context["media_image"]
    if expected == "None":
        assert media_image.camera_make is None
    else:
        # Strip quotes from expected value
        expected_value = expected.strip('"')
        assert media_image.camera_make == expected_value


@then(parsers.parse("the MediaImage camera_model should be {expected}"))
def step_then_camera_model(session_context, expected):
    media_image = session_context["media_image"]
    if expected == "None":
        assert media_image.camera_model is None
    else:
        # Strip quotes from expected value
        expected_value = expected.strip('"')
        assert media_image.camera_model == expected_value
