"""
SDC (Structured Data on Commons) safe merge functionality.

This module provides functions to safely merge SDC statements when a file
already exists on Commons. The merge strategy is additive and non-destructive:

- New properties (that don't exist) are added completely
- Existing properties are only enhanced if the main snak value matches
- Qualifiers and references are added without removing existing ones
- Conflicting values are never overwritten
"""

import logging

from curator.asyncapi import (
    EntityIdDataValue,
    EntityIdValueSnak,
    ExternalIdValueSnak,
    GlobeCoordinateDataValue,
    GlobeCoordinateValueSnak,
    NoValueSnak,
    QuantityDataValue,
    QuantityValueSnak,
    Reference,
    SomeValueSnak,
    Statement,
    StringDataValue,
    StringValueSnak,
    TimeDataValue,
    TimeValueSnak,
    UrlDataValue,
    UrlValueSnak,
)

# Type alias for any snak type
Snak = (
    EntityIdValueSnak
    | ExternalIdValueSnak
    | GlobeCoordinateValueSnak
    | QuantityValueSnak
    | StringValueSnak
    | TimeValueSnak
    | UrlValueSnak
    | NoValueSnak
    | SomeValueSnak
)

# Type alias for qualifiers dict
Qualifiers = dict[str, list[Snak]]

logger = logging.getLogger(__name__)


def _get_snak_datavalue(snak: Snak):
    """Get the datavalue from a snak, or None for novalue/somevalue"""
    if isinstance(snak, (NoValueSnak, SomeValueSnak)):
        return None
    return snak.datavalue


def _normalize_datavalue_for_comparison(dv) -> tuple[str, ...] | None:
    """
    Normalize a datavalue for comparison purposes
    """
    if dv is None:
        return None

    if isinstance(dv, EntityIdDataValue):
        return ("entity-id", dv.value.entity_type, str(dv.value.numeric_id))

    if isinstance(dv, StringDataValue):
        return ("string", dv.value)

    if isinstance(dv, QuantityDataValue):
        return ("quantity", str(dv.value.amount), dv.value.unit)

    if isinstance(dv, GlobeCoordinateDataValue):
        return ("coordinate", str(dv.value.latitude), str(dv.value.longitude))

    if isinstance(dv, TimeDataValue):
        return ("time", dv.value.time)

    if isinstance(dv, UrlDataValue):
        return ("url", dv.value)

    # Unknown type
    return ("unknown", str(dv))


def are_snaks_equal(snak1: Snak, snak2: Snak) -> bool:
    """
    Check if two snaks are equal by comparing their values
    """
    # Check if properties match
    if snak1.property != snak2.property:
        return False

    # For novalue and somevalue, just checking property and type is enough
    if isinstance(snak1, NoValueSnak) and isinstance(snak2, NoValueSnak):
        return True
    if isinstance(snak1, SomeValueSnak) and isinstance(snak2, SomeValueSnak):
        return True

    # For value snaks, compare the datavalue
    dv1 = _get_snak_datavalue(snak1)
    dv2 = _get_snak_datavalue(snak2)

    if dv1 is None or dv2 is None:
        return dv1 == dv2

    return _normalize_datavalue_for_comparison(
        dv1
    ) == _normalize_datavalue_for_comparison(dv2)


def merge_qualifiers(
    existing: Qualifiers, new_qualifiers: list[Snak], return_order: bool = False
) -> tuple[Qualifiers, list[str]]:
    """
    Merge new qualifiers into existing qualifiers without duplication
    """
    merged: Qualifiers = {}
    # Copy existing qualifiers
    for prop, snaks in existing.items():
        merged[prop] = list(snaks)  # Make a copy

    order: list[str] = list(existing.keys())

    for new_snak in new_qualifiers:
        prop = new_snak.property
        if not prop:
            continue

        # Check if this snak already exists
        prop_snaks = merged.get(prop, [])
        exists = any(
            are_snaks_equal(new_snak, existing_snak) for existing_snak in prop_snaks
        )

        if exists:
            continue

        if prop not in merged:
            merged[prop] = []
        merged[prop].append(new_snak)
        if prop not in order:
            order.append(prop)

    return merged, order


def _normalize_reference(ref: Reference) -> tuple:
    """
    Normalize a reference for comparison
    """
    items: list[tuple[str, ...]] = []
    for prop, snaks in ref.snaks.items():
        for snak in snaks:
            dv = _get_snak_datavalue(snak)

            if dv is None:
                # Handle novalue/somevalue
                snak_type = "novalue" if isinstance(snak, NoValueSnak) else "somevalue"
                items.append((prop, snak_type, ""))
            elif isinstance(snak, ExternalIdValueSnak):
                # External ID uses StringDataValue but should be identified separately
                items.append((prop, "external-id", dv.value))
            else:
                # Use the normalized datavalue for comparison
                normalized = _normalize_datavalue_for_comparison(dv)
                if normalized:
                    items.append((prop, *normalized))
                else:
                    items.append((prop, "unknown", str(dv)))

    return tuple(items)


def merge_references(
    existing: list[Reference], new_references: list[Reference]
) -> list[Reference]:
    """
    Merge new references into existing references without duplication
    """
    # Normalize existing references for comparison
    existing_normalized = [_normalize_reference(ref) for ref in existing]

    merged = list(existing)

    for new_ref in new_references:
        new_normalized = _normalize_reference(new_ref)

        # Check if this reference already exists
        if new_normalized not in existing_normalized:
            merged.append(new_ref)
            existing_normalized.append(new_normalized)

    return merged


def safe_merge_statement(
    existing_statements: list[Statement], new_statement: Statement
) -> list[Statement]:
    """
    Safely merge a new statement into existing statements for the same property.

    Merge strategy:
    - If no existing statement with the same mainsnak value, keep existing (don't add new)
    - If an existing statement has the same mainsnak value, merge qualifiers and references
    - Never overwrite existing values
    - Preserve existing statement id and mainsnak hash
    - Only create new Statement object if qualifiers/references actually changed
    """
    new_mainsnak = new_statement.mainsnak

    matching_idx = None
    for i, existing_stmt in enumerate(existing_statements):
        if are_snaks_equal(existing_stmt.mainsnak, new_mainsnak):
            matching_idx = i
            break

    if matching_idx is None:
        # No matching statement found
        if not existing_statements:
            # No existing statements, add the new one
            return [new_statement]
        else:
            # Have existing statements but none match, keep existing (don't add conflicting new one)
            return existing_statements

    existing_stmt = existing_statements[matching_idx]

    existing_qualifiers = existing_stmt.qualifiers
    new_qualifiers = new_statement.qualifiers
    new_qualifiers_list: list[Snak] = []
    for snaks in new_qualifiers.values():
        new_qualifiers_list.extend(snaks)

    merged_qualifiers, qualifiers_order = merge_qualifiers(
        existing_qualifiers, new_qualifiers_list
    )

    merged_references = merge_references(
        existing_stmt.references, new_statement.references
    )

    # Check if anything actually changed by comparing content
    # Note: merge functions always create new objects, so we check content equality
    qualifiers_changed = merged_qualifiers != existing_qualifiers or (
        qualifiers_order != existing_stmt.qualifiers_order
    )
    references_changed = merged_references != existing_stmt.references

    if not qualifiers_changed and not references_changed:
        # Nothing changed, return existing statements as-is
        return existing_statements

    merged_statement = Statement(
        mainsnak=existing_stmt.mainsnak,
        rank=existing_stmt.rank,
        qualifiers=merged_qualifiers,
        qualifiers_order=qualifiers_order,
        references=merged_references,
        type=existing_stmt.type,
        id=existing_stmt.id,
    )

    existing_statements[matching_idx] = merged_statement

    return existing_statements


def merge_sdc_statements(
    existing: list[Statement], new: list[Statement]
) -> list[Statement]:
    """
    Safely merge new SDC statements into existing SDC
    """
    # Group existing statements by property
    existing_by_property: dict[str, list[Statement]] = {}
    for stmt in existing:
        prop = stmt.mainsnak.property
        if prop:
            if prop not in existing_by_property:
                existing_by_property[prop] = []
            existing_by_property[prop].append(stmt)

    # Group new statements by property
    new_by_property: dict[str, list[Statement]] = {}
    for stmt in new:
        prop = stmt.mainsnak.property
        if prop:
            if prop not in new_by_property:
                new_by_property[prop] = []
            new_by_property[prop].append(stmt)

    # Merge statements for each property
    result: list[Statement] = []

    # First, add all existing statements (they may be modified)
    for prop, existing_stmts in existing_by_property.items():
        new_stmts = new_by_property.get(prop, [])

        if not new_stmts:
            # No new statements for this property, keep existing as is
            result.extend(existing_stmts)
            continue

        # For coordinate properties, preserve existing as-is without any merging
        # Check if any existing statement is a GlobeCoordinateValueSnak
        has_coordinate = any(
            isinstance(stmt.mainsnak, GlobeCoordinateValueSnak)
            for stmt in existing_stmts
        )
        if has_coordinate:
            result.extend(existing_stmts)
            del new_by_property[prop]
            continue

        # Merge each new statement into existing
        merged = existing_stmts
        for new_stmt in new_stmts:
            merged = safe_merge_statement(merged, new_stmt)

        result.extend(merged)

        # Mark as processed
        del new_by_property[prop]

    # Then, add any new properties that don't exist in existing
    for prop, new_stmts in new_by_property.items():
        result.extend(new_stmts)

    return result
