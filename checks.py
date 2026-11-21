"""Steps 6 and 7: parse the LLM reply, then check it against the input.

The main failure mode for this product is the AI inventing causes the data
doesn't support. These checks are where that gets caught:
  - categories the user never entered are dropped
  - "evidence" quotes that don't appear in the notes are removed and flagged
  - price/volume calls that contradict the unit maths are overridden
  - confidence is capped by how much evidence the user actually gave
"""

import json
import re

ALLOWED = {"volume", "price", "timing", "anomaly", "unexplained"}

# The most confidence a line can get, based on what the user gave us.
CONFIDENCE_CAP = {"quantified": 90, "noted": 75, "none": 35}
PENALTY_UNGROUNDED = 20
PENALTY_OVERRIDE = 15


class ParseError(Exception):
    pass


def parse_reply(text):
    """Get a dict out of the reply, even if the model wrapped it in a code fence."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.S)
    if fence:
        cleaned = fence.group(1)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ParseError("The AI reply was not JSON.")
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as e:
            raise ParseError(f"The AI reply could not be read as JSON ({e.msg}).")
    if not isinstance(data, dict):
        raise ParseError("The AI reply had the wrong shape.")
    return data


def _norm(s):
    return re.sub(r"\s+", " ", str(s).lower()).strip(" .\"'")


def _grounded(item, notes):
    """True if an evidence item is a computed fact or really appears in the notes."""
    text = _norm(item)
    if text.startswith("computed"):
        return True
    source = _norm(notes)
    if not text or not source:
        return False
    if text in source:
        return True
    # Allow small wording slips (dropped "the", changed punctuation), but most
    # of the meaningful words still have to come from the notes.
    words = [w for w in re.findall(r"[a-z0-9%]+", text) if len(w) > 3]
    if not words:
        return False
    source_words = set(re.findall(r"[a-z0-9%]+", source))
    return sum(w in source_words for w in words) / len(words) >= 0.8


def band(score):
    if score >= 75:
        return "High"
    if score >= 50:
        return "Medium"
    return "Low"


def logic_only_driver(row, reason):
    """Used when the AI fails or skips a line: show the maths, say nothing about cause."""
    return {
        "category": row["category"],
        "classification": row["hint"] if row["hint"] in ALLOWED else "unexplained",
        "explanation": reason,
        "evidence": [],
        "confidence": 20,
        "flags": ["No AI explanation for this line. Figures and classification come from the logic layer."],
        "row": row,
    }


def check_and_score(raw, analysis):
    """Returns the final, checked output that gets saved and shown."""
    by_name = {r["category"].lower(): r for r in analysis["material"]}
    drivers_in = raw.get("drivers") or []
    if not isinstance(drivers_in, list):
        drivers_in = []

    checked = []
    removed = []      # things the AI said that we threw away
    seen = set()
    for d in drivers_in:
        if not isinstance(d, dict):
            continue
        name = str(d.get("category", "")).strip()
        row = by_name.get(name.lower())
        if row is None:
            removed.append(f"Dropped an explanation for '{name}', which is not a material line in the input.")
            continue
        if row["category"].lower() in seen:
            continue
        seen.add(row["category"].lower())

        flags = []
        cls = str(d.get("classification", "")).strip().lower()
        if cls not in ALLOWED:
            flags.append(f"AI used an unknown classification '{cls}'. Replaced with the logic layer's call.")
            cls = row["hint"] if row["hint"] in ALLOWED else "unexplained"

        try:
            conf = float(d.get("confidence", 50))
        except (TypeError, ValueError):
            conf = 50.0
        conf = max(0.0, min(100.0, conf))

        # Evidence grounding
        good, bad = [], []
        for item in d.get("evidence") or []:
            (good if _grounded(item, row["notes"]) else bad).append(str(item))
        penalty = 0
        if bad:
            penalty += PENALTY_UNGROUNDED
            flags.append(f"{len(bad)} piece(s) of 'evidence' did not match the notes you entered and were removed.")
            removed.extend(f"{row['category']}: removed unsupported evidence \"{b}\"" for b in bad)

        # Unit maths beats the AI on price vs volume
        if row["hint"] in ("volume", "price") and cls in ("volume", "price") and cls != row["hint"]:
            flags.append(f"AI said '{cls}' but the unit numbers show '{row['hint']}'. Using the maths.")
            cls = row["hint"]
            penalty += PENALTY_OVERRIDE

        explanation = str(d.get("explanation", "")).strip() or "No explanation returned."

        # No evidence at all: whatever the AI wrote about the cause is a guess,
        # so it gets replaced with a plain statement of what we know.
        if row["evidence_level"] == "none":
            if cls not in ("unexplained", "anomaly"):
                flags.append("You gave no notes or units for this line, so the cause is marked as unexplained.")
                cls = "unexplained"
            removed.append(f"{row['category']}: replaced the AI's guess \"{explanation}\" because the input has no evidence for it")
            explanation = ("The input gives no reason for this movement, so no cause is suggested. "
                           "Check with the budget owner before the review.")

        cap = CONFIDENCE_CAP[row["evidence_level"]]
        final = max(5, min(conf, cap) - penalty)
        if conf > cap:
            flags.append(f"Confidence capped at {cap} because the input only has '{row['evidence_level']}' evidence.")

        checked.append({
            "category": row["category"],
            "classification": cls,
            "explanation": explanation,
            "evidence": good,
            "confidence": round(final),
            "flags": flags,
            "row": row,
        })

    # Any material line the AI skipped still shows up, with the maths only.
    for row in analysis["material"]:
        if row["category"].lower() not in seen:
            checked.append(logic_only_driver(row, "The AI did not return an explanation for this line."))

    checked.sort(key=lambda d: abs(d["row"]["impact"]), reverse=True)
    overall = _overall(checked)

    gaps = [str(g).strip() for g in (raw.get("data_gaps") or []) if str(g).strip()]
    return {
        "summary": str(raw.get("summary", "")).strip(),
        "drivers": checked,
        "data_gaps": gaps[:6],
        "removed": removed,
        "overall_confidence": overall,
        "overall_band": band(overall),
        "ai_used": True,
    }


def _overall(drivers):
    """Confidence for the whole report, weighted by how much each line moved."""
    weight = sum(abs(d["row"]["impact"]) for d in drivers)
    if not drivers or weight == 0:
        return 0
    return round(sum(d["confidence"] * abs(d["row"]["impact"]) for d in drivers) / weight)


def logic_only_result(analysis, reason):
    """Fallback when the LLM call or parsing fails. The report still works."""
    drivers = [logic_only_driver(r, "AI explanation unavailable. See the calculated figures.")
               for r in analysis["material"]]
    overall = _overall(drivers)
    return {
        "summary": "",
        "drivers": drivers,
        "data_gaps": [],
        "removed": [],
        "overall_confidence": overall,
        "overall_band": band(overall),
        "ai_used": False,
        "ai_error": reason,
    }
