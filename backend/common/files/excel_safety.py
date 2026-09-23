"""Shared xlsxwriter options that stop generated reports from becoming a formula-injection vector.

Uploaded source data - cell values, and CSV/XLSX header names - flows straight
into the generated .xlsx reports (failed-row samples, profiled min/max
values, column names, ...). By default xlsxwriter's write() auto-detects a
string starting with "=" (also "+", "-", "@") and stores it as a live
formula, so a crafted value like `=cmd|'/c calc'!A0` in an uploaded file
would execute for whoever opens the report in Excel. Disabling
strings_to_formulas makes xlsxwriter always store such values as plain text
instead. None of this codebase's report writers ever write an intentional
formula (checked: no write_formula() call anywhere), so this is a pure
safety gain with no feature loss.
"""

XLSXWRITER_SAFE_OPTIONS = {"strings_to_formulas": False}


def is_missing(value) -> bool:
    """Whether a cell value should be treated as blank.

    Report writers previously asked pandas this (``pd.isna``). Polars represents
    a blank cell as None rather than NaN, but NaN can still reach a report from
    a numeric aggregate - a mean over zero rows, say - so both are covered here.
    Getting this wrong is visible: a missed NaN is written into the workbook as
    the literal text "nan".
    """
    if value is None:
        return True

    return isinstance(value, float) and value != value
