from __future__ import annotations

from typing import Iterable


def _tail(name: str) -> str:
    return name.strip().lower().rsplit(".", 1)[-1]


def match_lov_name(
    candidates: Iterable[str],
    reference_name: str,
) -> str | None:
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

    if len(matches) == 1:
        return matches[0]

    return None
