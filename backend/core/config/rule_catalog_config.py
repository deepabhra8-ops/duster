"""DQ rule catalog.

Used to validate the "Applicable Rules" cells a user edits in the profile map.
Not imported from engine.rules.rule_registry directly: that module pulls in
PySpark, and this settings package is loaded by every code path, including ones
(CLI scripts, lightweight routes) that have no business paying PySpark's import
cost. This list is a deliberate duplicate of the rule IDs registered there and
must be kept in sync when a DQ rule is added. The engine remains the authority
at execution time; this is only an early, friendlier rejection of typos in the UI.

TODO(restructure phase 3): dedupe this against engine.rules.rule_registry via a
zero-import shared catalog module (common/dq_rule_catalog.py).
"""

VALID_RULE_IDS = (
    "DQ1",   # Completeness
    "DQ2",   # Date format
    "DQ3",   # String length
    "DQ4",   # Decimal precision
    "DQ5",   # Range
    "DQ6",   # Value
    "DQ7",   # Pattern
    "DQ8",   # List of values
    "DQ9",   # Foreign key
    "DQ10",  # Uniqueness
    "DQ11",  # Custom SQL
)
