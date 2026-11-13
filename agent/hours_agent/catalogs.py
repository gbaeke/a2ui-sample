"""The catalogs this agent can generate UI for."""

import json
from pathlib import Path

from a2ui.core import Catalog
from a2ui.core.basic_catalog import BasicCatalog
from a2ui.core.schema import ProtocolVersion

VERSION = ProtocolVersion.V1_0

# The contract shared with the web app: <repo>/catalog/hours_catalog.json.
HOURS_CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "catalog" / "hours_catalog.json"
)

basic_catalog = BasicCatalog(VERSION)
hours_catalog = Catalog.from_json(
    json.loads(HOURS_CATALOG_PATH.read_text(encoding="utf-8"))
)

BASIC_ID: str = basic_catalog.catalog_id
HOURS_ID: str = hours_catalog.catalog_id

CATALOGS = [basic_catalog, hours_catalog]
