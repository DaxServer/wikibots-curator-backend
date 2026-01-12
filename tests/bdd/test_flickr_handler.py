"""BDD tests for flickr_handler.feature"""
from curator.app.handler import get_handler_for_handler_type
from curator.asyncapi import ImageHandler
from curator.handlers.flickr_handler import FlickrHandler
from pytest_bdd import given, parsers, scenario, then, when


# --- Scenarios ---


@scenario(
    "features/flickr_handler.feature", "Flickr handler enum maps to FlickrHandler"
)
def test_flickr_enum_to_handler():
    pass


# --- GIVENS ---


@given(parsers.parse('the ImageHandler enum value is "{handler_value}"'))
def step_given_image_handler_enum(handler_value, session_context):
    session_context["handler_type"] = ImageHandler(handler_value)


# --- WHENS ---


@when("I get the handler for this type")
def step_when_get_handler(session_context):
    handler_type = session_context.get("handler_type")
    handler = get_handler_for_handler_type(handler_type)
    session_context["handler"] = handler


# --- THENS ---


@then("the FlickrHandler should be returned")
def step_then_flickr_handler_returned(session_context):
    assert isinstance(session_context["handler"], FlickrHandler)
