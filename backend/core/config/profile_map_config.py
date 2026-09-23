"""Profile-map field editing rules."""

# Profile-map cells a user may edit in the browser. Everything else in the map is
# computed by profiling and is read-only.
PROFILE_MAP_EDITABLE_FIELDS = (
    "CDE (X=Yes)",
    "Applicable Rules",
    "Rule Parameters",
    "Analyst Notes",
)

PROFILE_MAP_TEXT_FIELD_MAX_LEN = 2000
# Analyst Notes only - Rule Parameters keeps the larger limit above.
PROFILE_MAP_NOTES_MAX_LEN = 200
