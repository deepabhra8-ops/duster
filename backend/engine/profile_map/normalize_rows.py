from __future__ import annotations

import uuid
from typing import Any, Mapping

def normalize_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    normalized = []
    
    for row in rows:
        rules_str = str(row.get("Applicable Rules", "") or "").strip()

        if "," not in rules_str and ";" not in rules_str and "|" not in rules_str:
            new_row = dict(row)
            if new_row.get("row_id") is None:
                new_row["row_id"] = str(uuid.uuid4())
            normalized.append(new_row)
            continue

        rules = [
            r.strip().upper() 
            for r in rules_str.replace(";", ",").replace("|", ",").split(",") 
            if r.strip()
        ]
        
        if not rules:
            new_row = dict(row)
            if new_row.get("row_id") is None:
                new_row["row_id"] = str(uuid.uuid4())
            normalized.append(new_row)
            continue
            
        for rule in rules:
            new_row = dict(row)
            new_row["Applicable Rules"] = rule
            if new_row.get("row_id") is None:
                new_row["row_id"] = str(uuid.uuid4())
            normalized.append(new_row)
            
    return normalized
