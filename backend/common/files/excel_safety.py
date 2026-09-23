XLSXWRITER_SAFE_OPTIONS = {"strings_to_formulas": False}


def is_missing(value) -> bool:
    if value is None:
        return True

    return isinstance(value, float) and value != value
