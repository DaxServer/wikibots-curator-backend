from pathlib import Path

import yaml

from curator.asyncapi import (
    WS_CHANNEL_ADDRESS,
    RECEIVE_CLIENT_MESSAGE_TYPES,
    SEND_SERVER_MESSAGE_TYPES,
)


def _load_spec():
    root = Path(__file__).resolve().parents[1]
    path = root / "asyncapi.yml"
    content = path.read_text(encoding="utf-8")
    return yaml.safe_load(content)


def test_ws_channel_address_matches_spec():
    spec = _load_spec()
    assert WS_CHANNEL_ADDRESS == spec["channels"]["wsChannel"]["address"]


def test_message_types_match_spec():
    spec = _load_spec()
    operations = spec["operations"]
    components_messages = spec["components"]["messages"]

    receive_refs = [
        message["$ref"] for message in operations["ReceiveClientMessages"]["messages"]
    ]
    send_refs = [
        message["$ref"] for message in operations["SendServerMessages"]["messages"]
    ]

    def refs_to_types(refs):
        types = []
        for ref in refs:
            key = ref.split("/")[-1]
            name_value = components_messages[key]["name"]
            types.append(name_value)
        return types

    assert RECEIVE_CLIENT_MESSAGE_TYPES == refs_to_types(receive_refs)
    assert SEND_SERVER_MESSAGE_TYPES == refs_to_types(send_refs)
