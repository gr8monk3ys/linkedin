"""Provision custom fields on Twenty CRM objects for LinkedIn CLI data."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from linkedin.data.twenty_client import TwentyClient

# Colors for SELECT field options (Twenty expects hex colors)
_STATUS_COLORS = {
    "not_contacted": "#B0B0B0",
    "connection_sent": "#4A90D9",
    "connected": "#50C878",
    "messaged": "#FFD700",
    "responded": "#FF8C00",
    "call_scheduled": "#9370DB",
    "rejected": "#DC3545",
    "hired": "#28A745",
}

_PRIORITY_COLORS = {
    "high": "#DC3545",
    "medium": "#FFD700",
    "low": "#28A745",
}

# Field definitions: (field_name, field_type, options_or_none)
_PERSON_FIELDS: list[tuple[str, str, list[dict] | None]] = [
    ("contactStatus", "SELECT", [
        {"value": v, "label": v.replace("_", " ").title(), "color": _STATUS_COLORS[v]}
        for v in _STATUS_COLORS
    ]),
    ("followUpDate", "DATE", None),
    ("lastContactDate", "DATE_TIME", None),
    ("contactSource", "TEXT", None),
    ("contactNotes", "TEXT", None),
]

_COMPANY_FIELDS: list[tuple[str, str, list[dict] | None]] = [
    ("companyIndustry", "TEXT", None),
    ("whyTarget", "TEXT", None),
    ("companyPriority", "SELECT", [
        {"value": v, "label": v.title(), "color": _PRIORITY_COLORS[v]}
        for v in _PRIORITY_COLORS
    ]),
    ("companyNotes", "TEXT", None),
]

_LIST_FIELDS_QUERY = """
query ListFields($filter: fieldFilter) {
  fields(filter: $filter) {
    edges {
      node {
        id
        name
        type
      }
    }
  }
}
"""

_CREATE_FIELD_MUTATION = """
mutation CreateField($input: CreateFieldInput!) {
  createOneField(input: { field: $input }) {
    id
    name
  }
}
"""


def _get_existing_field_names(client: TwentyClient, object_name: str) -> set[str]:
    """Fetch the set of custom field names already on an object."""
    data = client.metadata_query(
        _LIST_FIELDS_QUERY,
        {"filter": {"objectMetadataId": {"eq": _get_object_metadata_id(client, object_name)}}},
    )
    edges = data.get("fields", {}).get("edges", [])
    return {edge["node"]["name"] for edge in edges}


def _get_object_metadata_id(client: TwentyClient, object_name: str) -> str:
    """Get the metadata ID for a standard object (person, company)."""
    query = """
    query {
      objects {
        edges {
          node {
            id
            nameSingular
          }
        }
      }
    }
    """
    data = client.metadata_query(query)
    for edge in data.get("objects", {}).get("edges", []):
        if edge["node"]["nameSingular"] == object_name:
            return edge["node"]["id"]
    raise ValueError(f"Object '{object_name}' not found in Twenty metadata")


def _create_field(
    client: TwentyClient,
    object_metadata_id: str,
    name: str,
    field_type: str,
    options: list[dict] | None = None,
) -> None:
    """Create a single custom field on a Twenty object."""
    field_input: dict = {
        "objectMetadataId": object_metadata_id,
        "name": name,
        "label": name[0].upper() + name[1:],  # camelCase -> Capitalized
        "type": field_type,
        "description": f"LinkedIn CLI: {name}",
    }
    if options is not None:
        field_input["options"] = options
    client.metadata_query(_CREATE_FIELD_MUTATION, {"input": field_input})


def _ensure_fields_on_object(
    client: TwentyClient,
    object_name: str,
    fields: list[tuple[str, str, list[dict] | None]],
) -> None:
    """Ensure all required custom fields exist on a Twenty object."""
    object_id = _get_object_metadata_id(client, object_name)
    existing = _get_existing_field_names(client, object_name)

    for name, field_type, options in fields:
        if name not in existing:
            _create_field(client, object_id, name, field_type, options)


def ensure_custom_fields(client: TwentyClient) -> None:
    """Provision all custom fields needed by the LinkedIn CLI. Idempotent."""
    _ensure_fields_on_object(client, "person", _PERSON_FIELDS)
    _ensure_fields_on_object(client, "company", _COMPANY_FIELDS)
