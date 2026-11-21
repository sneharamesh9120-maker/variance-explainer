"""Step 10: numbers for the admin dashboard.

The point of the dashboard is to watch the failure mode: how often the checks
had to step in, how confident reports are, and whether users trust them.
"""

import json
import os
from collections import Counter

import db

# Price per 1M tokens in USD. Zero on the Gemini free tier; set these in
# Secrets if you move to a paid tier so the dashboard shows real spend.
PRICE_IN = float(os.environ.get("PRICE_INPUT_PER_M", "0"))
PRICE_OUT = float(os.environ.get("PRICE_OUTPUT_PER_M", "0"))


def _avg(values):
    return round(sum(values) / len(values)) if values else 0


def dashboard_stats():
    with db._conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM reports ORDER BY id DESC").fetchall()]

    total = len(rows)
    ai_ok = [r for r in rows if r["ai_used"]]
    failures = [r for r in rows if not r["ai_used"]]
    p_tok = sum(r["prompt_tokens"] or 0 for r in rows)
    c_tok = sum(r["completion_tokens"] or 0 for r in rows)
    cost = p_tok / 1e6 * PRICE_IN + c_tok / 1e6 * PRICE_OUT

    classes = Counter()
    flags_by_type = Counter()
    for r in rows:
        try:
            result = json.loads(r["result_json"])
        except (TypeError, ValueError):
            continue
        for d in result.get("drivers", []):
            classes[d.get("classification", "unexplained")] += 1
            for f in d.get("flags", []):
                if "did not match the notes" in f:
                    flags_by_type["Unsupported evidence removed"] += 1
                elif "Using the maths" in f:
                    flags_by_type["Price/volume call overridden"] += 1
                elif "Confidence capped" in f:
                    flags_by_type["Confidence capped"] += 1
                elif "marked as unexplained" in f:
                    flags_by_type["Cause blocked (no evidence)"] += 1
                elif "No AI explanation" in f:
                    flags_by_type["Line skipped by AI"] += 1
                else:
                    flags_by_type["Other"] += 1
        for item in result.get("removed", []):
            if item.startswith("Dropped an explanation"):
                flags_by_type["Invented category dropped"] += 1
            elif item.startswith("Summary: removed"):
                flags_by_type["Wrong figure removed from summary"] += 1

    rated = [r for r in rows if r["feedback"] in ("up", "down")]
    up = sum(1 for r in rated if r["feedback"] == "up")

    bands = Counter(r["overall_band"] for r in rows)
    return {
        "total": total,
        "ai_success_rate": round(len(ai_ok) / total * 100) if total else 0,
        "failures": len(failures),
        "avg_confidence": _avg([r["overall_confidence"] for r in rows if r["overall_confidence"] is not None]),
        "avg_latency": round(sum(r["latency_ms"] or 0 for r in ai_ok) / len(ai_ok) / 1000, 1) if ai_ok else 0,
        "reports_with_interventions": sum(1 for r in rows if (r["flags_count"] or 0) + (r["removed_count"] or 0) > 0),
        "tokens_in": p_tok,
        "tokens_out": c_tok,
        "cost_usd": cost,
        "cost_per_report": cost / len(ai_ok) if ai_ok else 0,
        "classes": classes.most_common(),
        "class_max": max(classes.values()) if classes else 1,
        "flags": flags_by_type.most_common(),
        "bands": [(b, bands.get(b, 0)) for b in ("High", "Medium", "Low", "On plan")],
        "rated": len(rated),
        "trust_pct": round(up / len(rated) * 100) if rated else None,
        "recent_errors": [(r["id"], r["created_at"], r["ai_error"]) for r in failures[:5]],
        "reports": rows[:50],
    }
