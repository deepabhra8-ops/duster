"""Matches a DQ8 rule's LOV name against the LOV names actually on offer.

The two sides are written by different people at different times and rarely
agree character for character. A profile map's `Rule Parameters` cell might say
`CustomerName`, while the LOV CSV that supplies it is headed
`Customer.CustomerName` - the same list, qualified by its table. An exact dict
lookup treats those as unrelated, so the rule reports "check not run" against a
file that is sitting right there, correctly uploaded.

Matching is deliberately narrow: exact, then case-insensitive, then on the
trailing dot-segment. A tie on that last step resolves to nothing rather than to
a guess - validating a column against the wrong reference list is worse than
declining to validate it.

This lives under utils/ rather than engine/reference_data/ because both
ExecutionContext and LovProvider need it, and that package's __init__ imports
LovProvider, which imports ExecutionContext.
"""

from __future__ import annotations

from typing import Iterable


def _tail(name: str) -> str:
    """Return a name's trailing dot-segment, lowercased."""
    return name.strip().lower().rsplit(".", 1)[-1]


def match_lov_name(
    candidates: Iterable[str],
    reference_name: str,
) -> str | None:
    """Return the candidate a reference name refers to, or None.

    `candidates` are the names on offer - lov_tables keys, or a wide LOV file's
    column headers. The candidate is returned exactly as given, so the caller
    can use it as a key.
    """
    if not reference_name:
        return None

    available = [str(candidate) for candidate in candidates]

    if reference_name in available:
        return reference_name

    target = reference_name.strip().lower()

    for candidate in available:
        if candidate.strip().lower() == target:
            return candidate

    tail = _tail(reference_name)

    matches = [
        candidate
        for candidate in available
        if _tail(candidate) == tail
    ]

    # Two lists whose names end the same way (Customer.Status, Policy.Status)
    # against a bare `Status` is genuinely ambiguous; leave it to the caller to
    # report rather than picking one.
    if len(matches) == 1:
        return matches[0]

    return None
