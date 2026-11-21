"""Step 2 of the pipeline: check the form input before anything else runs.

Bad input is the cheapest problem to catch, so we stop here with a clear
message instead of sending junk to the logic layer or the LLM.
"""

import re

MIN_ROWS = 2
MAX_ROWS = 30
MAX_NOTE_LEN = 300
CURRENCIES = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}
ROW_TYPES = {"revenue", "cost"}


def _to_number(raw):
    """Turn '12,00,000' or '₹ 1,500.50' into a float. Returns None if blank."""
    if raw is None:
        return None
    text = str(raw).strip()
    if text == "":
        return None
    text = re.sub(r"[₹$€£,\s]", "", text)
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"'{raw}' is not a number")


def collect_rows(form):
    """Pull the repeating row fields out of the submitted form."""
    rows = []
    categories = form.getlist("category")
    for i in range(len(categories)):
        def field(name):
            values = form.getlist(name)
            return values[i] if i < len(values) else ""

        row = {
            "category": field("category"),
            "type": field("type"),
            "forecast": field("forecast"),
            "actual": field("actual"),
            "forecast_units": field("forecast_units"),
            "actual_units": field("actual_units"),
            "notes": field("notes"),
        }
        # skip rows the user left completely empty
        if any(str(v).strip() for k, v in row.items() if k != "type"):
            rows.append(row)
    return rows


def validate(form):
    """Returns (clean_data, errors). If errors is non-empty, clean_data is None."""
    errors = []
    title = (form.get("title") or "").strip()
    period = (form.get("period") or "").strip()
    currency = (form.get("currency") or "INR").strip().upper()

    if not title:
        errors.append("Give the report a name (for example 'October close, India retail').")
    elif len(title) > 120:
        errors.append("Report name is too long. Keep it under 120 characters.")
    if not period:
        errors.append("Add the period you are reviewing (for example 'Oct 2026').")
    if currency not in CURRENCIES:
        errors.append("Pick a currency from the list.")

    raw_rows = collect_rows(form)
    if len(raw_rows) < MIN_ROWS:
        errors.append(f"Add at least {MIN_ROWS} categories. One line on its own has nothing to compare against.")
    if len(raw_rows) > MAX_ROWS:
        errors.append(f"Up to {MAX_ROWS} categories per report. Group smaller lines together.")

    clean_rows = []
    seen = set()
    for n, r in enumerate(raw_rows, start=1):
        label = r["category"].strip() or f"Row {n}"
        prefix = f"{label}:"

        if not r["category"].strip():
            errors.append(f"Row {n}: category name is missing.")
        key = r["category"].strip().lower()
        if key and key in seen:
            errors.append(f"{prefix} this category appears twice. Merge the rows or rename one.")
        seen.add(key)

        if r["type"] not in ROW_TYPES:
            errors.append(f"{prefix} choose whether this is revenue or cost.")

        nums = {}
        for field in ("forecast", "actual", "forecast_units", "actual_units"):
            try:
                nums[field] = _to_number(r[field])
            except ValueError as e:
                errors.append(f"{prefix} {e}.")
                nums[field] = None

        if r["forecast"].strip() == "" or r["actual"].strip() == "":
            errors.append(f"{prefix} both forecast and actual are needed.")
        for field in ("forecast", "actual", "forecast_units", "actual_units"):
            if nums[field] is not None and nums[field] < 0:
                errors.append(f"{prefix} {field.replace('_', ' ')} can't be negative. Enter costs as positive amounts.")

        fu, au = nums["forecast_units"], nums["actual_units"]
        if (fu is None) != (au is None):
            errors.append(f"{prefix} fill in both unit fields or leave both empty.")

        notes = r["notes"].strip()
        if len(notes) > MAX_NOTE_LEN:
            errors.append(f"{prefix} notes are too long ({len(notes)} characters, max {MAX_NOTE_LEN}).")

        clean_rows.append({
            "category": r["category"].strip(),
            "type": r["type"],
            "forecast": nums["forecast"] or 0.0,
            "actual": nums["actual"] or 0.0,
            "forecast_units": fu,
            "actual_units": au,
            "notes": notes,
        })

    if errors:
        return None, errors

    return {
        "title": title,
        "period": period,
        "currency": currency,
        "symbol": CURRENCIES[currency],
        "rows": clean_rows,
    }, []
