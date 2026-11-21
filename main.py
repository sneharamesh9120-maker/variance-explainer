"""Variance Explainer: why did we miss the forecast?

Pipeline for every report:
  form -> validate -> logic layer -> prompt -> LLM -> parse -> checks/confidence
  -> save to database -> show structured report -> admin dashboard
"""

import os
from datetime import datetime, timezone

from flask import Flask, render_template, request

from checks import ParseError, check_and_score, logic_only_result, parse_reply
from llm import LLMError, call_llm
from logic import analyse
from prompt import build_messages
from validation import CURRENCIES, validate

# All files sit in one folder: page templates, CSS and JS are loaded from here.
app = Flask(__name__, template_folder=".", static_folder=None)


@app.template_filter("money")
def money(value, symbol=""):
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol}{abs(value):,.0f}"


@app.template_filter("pct")
def pct(value):
    if value is None:
        return "n/a"
    return f"{value:+.1f}%"


@app.route("/")
def index():
    return render_template("index.html", currencies=CURRENCIES, form=None, errors=[])


@app.route("/analyse", methods=["POST"])
def run_analysis():
    data, errors = validate(request.form)
    if errors:
        return render_template("index.html", currencies=CURRENCIES, form=request.form, errors=errors), 400

    analysis = analyse(data)
    if not analysis["material"]:
        result = logic_only_result(analysis, "Nothing passed the materiality rule.")
        result["ai_used"] = True
        result["summary"] = "Every line is close to forecast or too small to matter. Nothing needs explaining."
    else:
        try:
            reply = call_llm(build_messages(data, analysis))
            result = check_and_score(parse_reply(reply["text"]), analysis)
        except (LLMError, ParseError) as e:
            result = logic_only_result(analysis, str(e))

    rec = {"id": "draft", "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")}
    return render_template("report.html", rec=rec, data=data, analysis=analysis, result=result)


@app.errorhandler(404)
def not_found(_):
    return render_template("message.html", title="Not found", message="That page doesn't exist."), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
