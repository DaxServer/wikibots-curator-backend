from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Any, Set

import yaml
import re


def _to_snake_case(name: str) -> str:
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def load_spec(path: Path) -> Dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    data: Dict[str, Any] = yaml.safe_load(content)
    return data


def _message_refs(messages: List[Dict[str, Any]]) -> List[str]:
    refs: List[str] = []
    for message in messages:
        ref = message.get("$ref")
        if isinstance(ref, str):
            refs.append(ref)
    return refs


def _refs_to_types(refs: List[str], components_messages: Dict[str, Any]) -> List[str]:
    types: List[str] = []
    for ref in refs:
        parts = ref.split("/")
        key = parts[-1]
        message_schema = components_messages.get(key)
        if not isinstance(message_schema, dict):
            continue
        name_value = message_schema.get("name")
        if isinstance(name_value, str):
            types.append(name_value)
    return types


def _ref_name(ref: str) -> str:
    parts = ref.split("/")
    return parts[-1]


def _collect_schema_refs_from_schema(schema: Dict[str, Any], out: Set[str]) -> None:
    ref = schema.get("$ref")
    if isinstance(ref, str):
        out.add(_ref_name(ref))
        return

    schema_type = schema.get("type")
    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            _collect_schema_refs_from_schema(items, out)
        return

    if schema_type == "object":
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            _collect_schema_refs_from_schema(additional, out)
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for prop_schema in properties.values():
                if isinstance(prop_schema, dict):
                    _collect_schema_refs_from_schema(prop_schema, out)


def _collect_schema_refs_from_messages(components_messages: Dict[str, Any]) -> Set[str]:
    names: Set[str] = set()
    for message in components_messages.values():
        payload = message.get("payload")
        if not isinstance(payload, dict):
            continue
        properties = payload.get("properties")
        if not isinstance(properties, dict):
            continue
        data_schema = properties.get("data")
        if isinstance(data_schema, dict):
            _collect_schema_refs_from_schema(data_schema, names)
    return names


def _python_type_for_schema(
    schema: Dict[str, Any],
    components_schemas: Dict[str, Any],
    generated_schema_classes: Dict[str, List[str]],
) -> str:
    if not schema:
        return "Any"

    ref = schema.get("$ref")
    if isinstance(ref, str):
        name = _ref_name(ref)
        schema_def = components_schemas.get(name)
        if not isinstance(schema_def, dict):
            return "str"

        one_of = schema_def.get("oneOf")
        if isinstance(one_of, list):
            member_types: List[str] = []
            for member in one_of:
                if not isinstance(member, dict):
                    continue
                member_ref = member.get("$ref")
                if not isinstance(member_ref, str):
                    continue
                member_name = _ref_name(member_ref)
                member_schema = components_schemas.get(member_name)
                if not isinstance(member_schema, dict):
                    continue
                if member_schema.get("type") != "object":
                    continue
                if member_name not in generated_schema_classes:
                    _generate_schema_class(
                        member_name,
                        member_schema,
                        components_schemas,
                        generated_schema_classes,
                    )
                member_types.append(member_name)

            if member_types:
                joined = ", ".join(member_types)
                return f"Union[{joined}]"
            return "str"

        if schema_def.get("type") == "object":
            if name not in generated_schema_classes:
                _generate_schema_class(
                    name,
                    schema_def,
                    components_schemas,
                    generated_schema_classes,
                )
            return name

    schema_type = schema.get("type")

    if schema_type == "string":
        return "str"
    if schema_type == "integer":
        return "int"
    if schema_type == "number":
        return "float"
    if schema_type == "boolean":
        return "bool"

    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            item_type = _python_type_for_schema(
                items,
                components_schemas,
                generated_schema_classes,
            )
            return f"List[{item_type}]"
        return "List[str]"

    if schema_type == "object":
        additional = schema.get("additionalProperties")
        if isinstance(additional, dict):
            value_type = _python_type_for_schema(
                additional,
                components_schemas,
                generated_schema_classes,
            )
            return f"Dict[str, {value_type}]"

    return "str"


def _generate_schema_class(
    name: str,
    schema: Dict[str, Any],
    components_schemas: Dict[str, Any],
    generated_schema_classes: Dict[str, List[str]],
) -> None:
    if name in generated_schema_classes:
        return

    if schema.get("type") != "object":
        return

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return

    required_list = schema.get("required") or []
    required = set(required_list)

    class_lines: List[str] = []
    class_lines.append("@dataclass")
    class_lines.append(f"class {name}:")

    ordered_items = list(properties.items())
    required_items = [item for item in ordered_items if item[0] in required]
    optional_items = [item for item in ordered_items if item[0] not in required]

    for prop_name, prop_schema in required_items + optional_items:
        if not isinstance(prop_schema, dict):
            continue

        field_type = _python_type_for_schema(
            prop_schema,
            components_schemas,
            generated_schema_classes,
        )

        is_required = prop_name in required
        is_nullable = bool(prop_schema.get("nullable"))

        annotated_type = field_type
        if not is_required or is_nullable:
            annotated_type = f"Optional[{field_type}]"

        if is_required and not is_nullable:
            class_lines.append(f"    {prop_name}: {annotated_type}")
        else:
            class_lines.append(f"    {prop_name}: {annotated_type} = None")

    if len(class_lines) == 2:
        class_lines.append("    pass")

    generated_schema_classes[name] = class_lines


def generate_code(spec: Dict[str, Any]) -> str:
    channels = spec["channels"]
    ws_channel = channels["wsChannel"]
    address_value = ws_channel["address"]

    operations = spec["operations"]
    receive_client = operations["ReceiveClientMessages"]
    send_server = operations["SendServerMessages"]

    receive_refs = _message_refs(receive_client["messages"])
    send_refs = _message_refs(send_server["messages"])

    components = spec["components"]
    components_messages = components["messages"]
    components_schemas = components["schemas"]

    receive_types = _refs_to_types(receive_refs, components_messages)
    send_types = _refs_to_types(send_refs, components_messages)

    receive_message_keys = [_ref_name(ref) for ref in receive_refs]
    send_message_keys = [_ref_name(ref) for ref in send_refs]

    schema_refs = _collect_schema_refs_from_messages(components_messages)
    needed_schema_classes = {name for name in schema_refs if name in components_schemas}

    generated_schema_classes: Dict[str, List[str]] = {}
    for name in sorted(needed_schema_classes):
        _generate_schema_class(
            name,
            components_schemas[name],
            components_schemas,
            generated_schema_classes,
        )

    lines: List[str] = []
    lines.append('"""Auto-generated from asyncapi.yml. Do not edit by hand."""')
    lines.append("")
    lines.append("from dataclasses import dataclass")
    lines.append("from typing import Literal, Union, List, Optional, Dict, Any")
    lines.append("from fastapi import WebSocket")
    lines.append("from pydantic import TypeAdapter")
    lines.append("")
    lines.append("")
    lines.append(f'WS_CHANNEL_ADDRESS: str = "{address_value}"')
    lines.append("")
    lines.append("")
    lines.append(
        f"RECEIVE_CLIENT_MESSAGE_TYPES: List[str] = {receive_types!r}",
    )
    lines.append(
        f"SEND_SERVER_MESSAGE_TYPES: List[str] = {send_types!r}",
    )
    lines.append("")

    client_literal_args = ", ".join(f'"{t}"' for t in receive_types)
    server_literal_args = ", ".join(f'"{t}"' for t in send_types)
    lines.append(
        f"ClientMessageType = Literal[{client_literal_args}]",
    )
    lines.append(
        f"ServerMessageType = Literal[{server_literal_args}]",
    )
    lines.append("")

    for class_lines in generated_schema_classes.values():
        lines.append("")
        lines.extend(class_lines)

    inline_data_classes: Dict[str, List[str]] = {}

    def ensure_inline_data_class(message_key: str, data_schema: Dict[str, Any]) -> str:
        name = f"{message_key}Data"
        if name in inline_data_classes:
            return name

        properties = data_schema.get("properties")
        required_list = data_schema.get("required") or []
        required = set(required_list)

        class_lines: List[str] = []
        class_lines.append("@dataclass")
        class_lines.append(f"class {name}:")

        if not isinstance(properties, dict):
            class_lines.append("    pass")
            inline_data_classes[name] = class_lines
            return name

        ordered_items = list(properties.items())
        required_items = [item for item in ordered_items if item[0] in required]
        optional_items = [item for item in ordered_items if item[0] not in required]

        for prop_name, prop_schema in required_items + optional_items:
            if not isinstance(prop_schema, dict):
                continue

            field_type = _python_type_for_schema(
                prop_schema,
                components_schemas,
                generated_schema_classes,
            )

            is_required = prop_name in required
            is_nullable = bool(prop_schema.get("nullable"))

            annotated_type = field_type
            if not is_required or is_nullable:
                annotated_type = f"Optional[{field_type}]"

            if is_required and not is_nullable:
                class_lines.append(f"    {prop_name}: {annotated_type}")
            else:
                class_lines.append(f"    {prop_name}: {annotated_type} = None")

        if len(class_lines) == 2:
            class_lines.append("    pass")

        inline_data_classes[name] = class_lines
        return name

    message_class_names: Dict[str, str] = {}
    message_info: Dict[str, tuple[str, str]] = {}

    for key, message_schema in components_messages.items():
        payload = message_schema.get("payload")
        if not isinstance(payload, dict):
            continue

        properties = payload.get("properties")
        if not isinstance(properties, dict):
            continue

        type_schema = properties.get("type")
        data_schema = properties.get("data")
        if not isinstance(type_schema, dict) or not isinstance(data_schema, dict):
            continue

        enum_values = type_schema.get("enum") or []
        literal_value = enum_values[0] if enum_values else message_schema.get("name")

        if data_schema.get("type") == "object" and "properties" in data_schema:
            data_type_name = ensure_inline_data_class(key, data_schema)
            data_type = data_type_name
        else:
            data_type = _python_type_for_schema(
                data_schema,
                components_schemas,
                generated_schema_classes,
            )

        class_name = f"{key}Message"
        message_class_names[key] = class_name
        message_info[key] = (literal_value, data_type)

        lines.append("")
        lines.append("@dataclass")
        lines.append(f"class {class_name}:")
        lines.append(f'    type: Literal["{literal_value}"]')
        lines.append(f'    data: "{data_type}"')

    for class_lines in inline_data_classes.values():
        lines.append("")
        lines.extend(class_lines)

    client_members = [f"{key}Message" for key in receive_message_keys]
    server_members = [f"{key}Message" for key in send_message_keys]

    if client_members:
        lines.append("")
        lines.append("ClientMessage = Union[")
        for member in client_members:
            lines.append(f"    {member},")
        lines.append("]")
    else:
        lines.append("")
        lines.append("ClientMessage = Any")

    if server_members:
        lines.append("")
        lines.append("ServerMessage = Union[")
        for member in server_members:
            lines.append(f"    {member},")
        lines.append("]")
    else:
        lines.append("")
        lines.append("ServerMessage = Any")

    lines.append("")
    lines.append("_ClientMessageAdapter = TypeAdapter(ClientMessage)")
    lines.append("_ServerMessageAdapter = TypeAdapter(ServerMessage)")
    lines.append("")
    lines.append("class AsyncAPIWebSocket(WebSocket):")
    lines.append(
        '    async def receive_json(self, mode: str = "text") -> ClientMessage:'
    )
    lines.append("        data = await super().receive_json(mode=mode)")
    lines.append("        return _ClientMessageAdapter.validate_python(data)")
    lines.append("")
    lines.append(
        '    async def send_json(self, data: ServerMessage, mode: str = "text") -> None:'
    )
    lines.append(
        "        await super().send_json(_ServerMessageAdapter.dump_python(data, mode='json'), mode=mode)"
    )

    for key in send_message_keys:
        if key not in message_info:
            continue
        literal_value, data_type = message_info[key]
        method_name = f"send_{_to_snake_case(key)}"
        class_name = message_class_names[key]

        lines.append("")
        lines.append(f"    async def {method_name}(self, data: {data_type}) -> None:")
        lines.append(
            f'        await self.send_json({class_name}(type="{literal_value}", data=data))'
        )

    return "\n".join(lines)


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    spec_path = project_root / "asyncapi.yml"
    spec = load_spec(spec_path)
    code = generate_code(spec)
    target = project_root / "src" / "curator" / "asyncapi.py"
    target.write_text(code, encoding="utf-8")


if __name__ == "__main__":
    main()
