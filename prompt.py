"""Step 4: build the prompt from the logic layer's facts.

Only material lines go in. Every number is pre-calculated, and the notes are
passed word for word so the output checker can match quotes against them later.
"""

import json

SYSTEM_PROMPT = """You help a finance analyst explain forecast vs actual variances to leadership.

Hard rules:
1. Explain ONLY the lines given in MATERIAL_LINES. Do not mention any other category.
2. A cause must come from that line's "notes" or from its computed numbers. Do not add causes
   from general knowledge (market conditions, seasonality, competition, inflation, etc.) unless
   the notes say so.
3. If a line has no notes and no price/volume split, say plainly that the data does not explain it,
   use classification "unexplained" (or "anomaly" if logic_hint is "anomaly"), and add a question
   for the business owner to data_gaps.
4. Do not calculate new numbers. Use the figures given.
5. Each item in "evidence" must be either an exact quote copied from that line's notes, or a fact
   starting with "computed:" taken from the numbers given.
6. classification must be one of: volume, price, timing, anomaly, unexplained.
   If logic_hint is volume or price, prefer it, because it comes from the unit maths.
7. confidence is 0 to 100: how well the evidence supports your explanation, not how sure you sound.

Return JSON only, in this shape:
{
  "summary": "3 or 4 plain sentences a CFO could read out. Lead with the net result.",
  "drivers": [
    {
      "category": "exact category name",
      "classification": "volume|price|timing|anomaly|unexplained",
      "explanation": "1 or 2 sentences",
      "evidence": ["exact quote from notes", "computed: ..."],
      "confidence": 0
    }
  ],
  "data_gaps": ["a specific question to ask someone, for lines the data can't explain"]
}"""


def _round(x):
    return None if x is None else round(x, 2)


def build_messages(data, analysis):
    t = analysis["totals"]
    lines = []
    for r in analysis["material"]:
        line = {
            "category": r["category"],
            "type": r["type"],
            "forecast": _round(r["forecast"]),
            "actual": _round(r["actual"]),
            "variance": _round(r["variance"]),
            "variance_pct": _round(r["variance_pct"]),
            "effect_on_profit": r["direction"],
            "share_of_total_movement_pct": round(r["share"] * 100, 1),
            "key_driver": r["key_driver"],
            "logic_hint": r["hint"],
            "logic_reason": r["signals"],
            "notes": r["notes"] or "",
        }
        if r["pvm"]:
            line["price_volume_split"] = {k: _round(v) for k, v in r["pvm"].items()}
        lines.append(line)

    payload = {
        "report": data["title"],
        "period": data["period"],
        "currency": data["currency"],
        "net_forecast": _round(t["net_forecast"]),
        "net_actual": _round(t["net_actual"]),
        "net_variance": _round(t["net_variance"]),
        "net_variance_pct": _round(t["net_variance_pct"]),
        "lines_not_material_count": len(analysis["rows"]) - len(analysis["material"]),
        "MATERIAL_LINES": lines,
    }

    user_msg = "Explain these variances. Data:\n" + json.dumps(payload, indent=2)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
