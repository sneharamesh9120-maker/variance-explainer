"""Variance Explainer: why did we miss the forecast?

Pipeline for every report:
  form -> validate -> logic layer -> prompt -> LLM -> parse -> checks/confidence
  -> save to database -> show structured report -> admin dashboard
"""

import os
from datetime import datetime, timezone

from flask import Flask, render_template, request

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
    # Logic layer comes next. For now, confirm the input is clean.
    return render_template("message.html", title="Input looks good",
                           message=f"{len(data['rows'])} categories received for {data['period']}. "
                                   "Analysis is not built yet.")


@app.errorhandler(404)
def not_found(_):
    return render_template("message.html", title="Not found", message="That page doesn't exist."), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
