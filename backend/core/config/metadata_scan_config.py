"""Catalog-scan bounds."""

import os


# Upper bounds on a catalog walk, so one enormous source can't stall a scan
# indefinitely (services/metadata/metadata_scan_service.py).
METADATA_SCAN_MAX_SCHEMAS = int(os.getenv("METADATA_SCAN_MAX_SCHEMAS", "50"))
METADATA_SCAN_MAX_TABLES_PER_SCHEMA = int(
    os.getenv("METADATA_SCAN_MAX_TABLES_PER_SCHEMA", "200")
)
