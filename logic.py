"""Step 3: the logic layer. Everything here is plain maths and rules.

The AI never calculates a number. It only gets the facts this file works out,
which is the main defence against it inventing causes or figures.
"""

import re

# Thresholds. Kept in one place so they are easy to explain and tune.
MATERIAL_PCT = 5.0          # a line must move at least 5% ...
MATERIAL_SHARE = 0.005      # ... and by at least 0.5% of total forecast
ANOMALY_PCT = 50.0          # a swing this big gets flagged as an anomaly
KEY_DRIVER_COVERAGE = 0.80  # key drivers = lines that explain 80% of the movement

TIMING_WORDS = [
    "delay", "delayed", "deferred", "defer", "postponed", "pushed", "slipped",
    "moved to", "next month", "next quarter", "pulled forward", "brought forward",
    "early", "accrual", "accrued", "invoice timing", "billing cycle", "phasing",
]

PRICE_VOLUME_SPLIT = 0.6  # one effect must be 60%+ of the gross movement to "win"


def _pct(var, forecast):
    if forecast == 0:
        return None
    return var / forecast * 100


def _timing_hit(notes):
    text = notes.lower()
    for word in TIMING_WORDS:
        if re.search(r"\b" + re.escape(word), text):
            return word
    return None


def price_volume_split(row):
    """Classic price/volume split. Returns None when units are not given.

    volume effect = (actual units - forecast units) x forecast price
    price effect  = (actual price - forecast price) x actual units
    The two always add up to the total variance.
    """
    fu, au = row["forecast_units"], row["actual_units"]
    if fu is None or au is None or fu == 0:
        return None
    f_price = row["forecast"] / fu
    a_price = row["actual"] / au if au else f_price
    volume = (au - fu) * f_price
    price = (a_price - f_price) * au
    return {
        "forecast_price": f_price,
        "actual_price": a_price,
        "volume_effect": volume,
        "price_effect": price,
    }


def classify_hint(row, pct, pvm):
    """Rule-based first guess at the type of variance, with the reason."""
    signals = []
    hit = _timing_hit(row["notes"]) if row["notes"] else None
    if hit:
        signals.append(f"Notes mention '{hit}', which points to timing.")
        return "timing", signals

    if pvm:
        gross = abs(pvm["volume_effect"]) + abs(pvm["price_effect"])
        if gross > 0:
            vol_share = abs(pvm["volume_effect"]) / gross
            if vol_share >= PRICE_VOLUME_SPLIT:
                signals.append(f"Units moved more than price: {vol_share:.0%} of the gross movement is volume.")
                return "volume", signals
            if (1 - vol_share) >= PRICE_VOLUME_SPLIT:
                signals.append(f"Price per unit moved more than units: {1 - vol_share:.0%} of the gross movement is price.")
                return "price", signals
            signals.append("Price and volume both moved by similar amounts.")
            return "price + volume", signals

    if row["forecast"] == 0 and row["actual"] > 0:
        signals.append("Nothing was forecast for this line but money came in or went out.")
        return "anomaly", signals
    if row["actual"] == 0 and row["forecast"] > 0:
        signals.append("Forecast was set but actual is zero.")
        return "anomaly", signals
    if pct is not None and abs(pct) >= ANOMALY_PCT:
        signals.append(f"A {abs(pct):.0f}% swing is beyond the {ANOMALY_PCT:.0f}% anomaly threshold.")
        return "anomaly", signals

    signals.append("No units and no explanation given, so the data can't say why this moved.")
    return "unexplained", signals


def analyse(data):
    rows = data["rows"]
    total_forecast = sum(r["forecast"] for r in rows)
    material_floor = total_forecast * MATERIAL_SHARE
    steps = []
    steps.append(f"Checked {len(rows)} lines with a combined forecast of {total_forecast:,.0f}.")
    steps.append(
        f"Materiality rule: a line counts if it moved {MATERIAL_PCT:.0f}% or more AND by at least "
        f"{material_floor:,.0f} ({MATERIAL_SHARE:.1%} of total forecast)."
    )

    out_rows = []
    for r in rows:
        var = r["actual"] - r["forecast"]
        pct = _pct(var, r["forecast"])
        # For the bottom line, more revenue is good and more cost is bad.
        impact = var if r["type"] == "revenue" else -var
        if var == 0:
            direction = "on plan"
        else:
            direction = "favourable" if impact > 0 else "unfavourable"

        if r["forecast"] == 0:
            material = r["actual"] != 0 and abs(var) >= material_floor
        else:
            material = abs(pct) >= MATERIAL_PCT and abs(var) >= material_floor

        pvm = price_volume_split(r)
        hint, signals = classify_hint(r, pct, pvm)

        if pvm:
            evidence = "quantified"
        elif r["notes"]:
            evidence = "noted"
        else:
            evidence = "none"

        out_rows.append({
            **r,
            "variance": var,
            "variance_pct": pct,
            "impact": impact,
            "direction": direction,
            "material": material,
            "pvm": pvm,
            "hint": hint,
            "signals": signals,
            "evidence_level": evidence,
            "share": 0.0,
            "key_driver": False,
        })

    material_rows = [r for r in out_rows if r["material"]]
    total_abs = sum(abs(r["impact"]) for r in out_rows) or 1.0
    for r in out_rows:
        r["share"] = abs(r["impact"]) / total_abs

    # Biggest contributors first; key drivers are the ones that make up 80%.
    material_rows.sort(key=lambda r: abs(r["impact"]), reverse=True)
    running = 0.0
    for r in material_rows:
        if running < KEY_DRIVER_COVERAGE:
            r["key_driver"] = True
        running += r["share"]

    rev_f = sum(r["forecast"] for r in rows if r["type"] == "revenue")
    rev_a = sum(r["actual"] for r in rows if r["type"] == "revenue")
    cost_f = sum(r["forecast"] for r in rows if r["type"] == "cost")
    cost_a = sum(r["actual"] for r in rows if r["type"] == "cost")
    net_f, net_a = rev_f - cost_f, rev_a - cost_a

    immaterial = len(out_rows) - len(material_rows)
    steps.append(
        f"{len(material_rows)} lines passed the materiality rule. {immaterial} were treated as noise "
        f"and not sent to the AI."
    )
    key = [r["category"] for r in material_rows if r["key_driver"]]
    if key:
        steps.append(f"Key drivers (together about {KEY_DRIVER_COVERAGE:.0%} of the movement): {', '.join(key)}.")
    n_pvm = sum(1 for r in out_rows if r["pvm"])
    if n_pvm:
        steps.append(f"Split {n_pvm} line(s) into price and volume effects using the unit numbers.")
    no_ev = [r["category"] for r in material_rows if r["evidence_level"] == "none"]
    if no_ev:
        steps.append(
            f"No notes or units for: {', '.join(no_ev)}. The AI is told to say the cause is unknown "
            f"rather than guess."
        )

    return {
        "rows": out_rows,
        "material": material_rows,
        "steps": steps,
        "totals": {
            "revenue_forecast": rev_f, "revenue_actual": rev_a,
            "cost_forecast": cost_f, "cost_actual": cost_a,
            "net_forecast": net_f, "net_actual": net_a,
            "net_variance": net_a - net_f,
            "net_variance_pct": _pct(net_a - net_f, net_f) if net_f else None,
            "total_forecast": total_forecast,
            "material_floor": material_floor,
        },
        "thresholds": {
            "material_pct": MATERIAL_PCT,
            "material_share": MATERIAL_SHARE,
            "anomaly_pct": ANOMALY_PCT,
        },
    }
