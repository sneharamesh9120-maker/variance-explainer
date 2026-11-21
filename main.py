"""Variance Explainer: why did we miss the forecast?

Pipeline for every report:
  form -> validate -> logic layer -> prompt -> LLM -> parse -> checks/confidence
  -> save to database -> show structured report -> admin dashboard
"""

import os

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

import admin
import db
from checks import ParseError, check_and_score, logic_only_result, parse_reply
from llm import LLMError, call_llm
from logic import analyse
from prompt import build_messages
from validation import CURRENCIES, validate

# All files sit in one folder: page templates, CSS and JS are loaded from here.
app = Flask(__name__, template_folder=".", static_folder=None)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-only-change-me")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

db.init_db()


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
    meta = {}

    if not analysis["material"]:
        result = logic_only_result(analysis, "Nothing passed the materiality rule, so there was nothing to explain.")
        result["ai_used"] = True  # not a failure, just nothing to send
        result["summary"] = (
            f"Every line is within {analysis['thresholds']['material_pct']:.0f}% of forecast or too small to matter. "
            "No variance needs explaining this period."
        )
    else:
        try:
            reply = call_llm(build_messages(data, analysis))
            meta = reply
            raw = parse_reply(reply["text"])
            result = check_and_score(raw, analysis)
        except (LLMError, ParseError) as e:
            result = logic_only_result(analysis, str(e))

    report_id = db.save_report(data, analysis, result, meta)
    return redirect(url_for("view_report", report_id=report_id))


@app.route("/report/<int:report_id>")
def view_report(report_id):
    rec = db.get_report(report_id)
    if not rec:
        abort(404)
    return render_template("report.html", rec=rec, data=rec["input"],
                           analysis=rec["analysis"], result=rec["result"])


@app.route("/report/<int:report_id>/feedback", methods=["POST"])
def feedback(report_id):
    value = request.form.get("value")
    if value in ("up", "down"):
        db.save_feedback(report_id, value, request.form.get("note", ""))
        flash("Thanks. Feedback saved.")
    return redirect(url_for("view_report", report_id=report_id))


@app.route("/history")
def history():
    return render_template("history.html", reports=db.list_reports())


def _admin_ok():
    return not ADMIN_PASSWORD or session.get("is_admin")


@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
        else:
            flash("Wrong password.")
        return redirect(url_for("admin_dashboard"))
    if not _admin_ok():
        return render_template("admin_login.html")
    return render_template("admin.html", s=admin.dashboard_stats(), open_mode=not ADMIN_PASSWORD)


@app.route("/admin/delete/<int:report_id>", methods=["POST"])
def admin_delete(report_id):
    if not _admin_ok():
        abort(403)
    db.delete_report(report_id)
    flash(f"Report #{report_id} deleted.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("index"))


@app.errorhandler(404)
def not_found(_):
    return render_template("message.html", title="Not found",
                           message="That report doesn't exist. It may have been deleted."), 404


@app.errorhandler(500)
def server_error(_):
    return render_template("message.html", title="Something broke",
                           message="The app hit an unexpected error. Your input was not lost on our side, "
                                   "but please go back and try again."), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
