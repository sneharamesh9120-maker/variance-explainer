# Variance Explainer

Month-end, leadership asks "why did we miss the forecast?". This app helps a finance analyst answer that with reasons the data can back up.

You enter forecast and actual by category, with optional units and notes. The app does the maths first (variance, materiality, biggest contributors, price/volume split), then asks an LLM to explain only the lines that matter, using only your notes as the source of causes. The reply is checked before you see it.

The product brief is in `docs/Variance_Explainer_Product_Brief.pdf`.

## How a report is built

1. **Input form**: structured table, no chat box
2. **Validation**: numbers, duplicates, missing fields, unit pairs (`validation.py`)
3. **Logic layer**: variance %, materiality rule, key drivers, price/volume split, rule-based classification (`logic.py`)
4. **Prompt**: only material lines, pre-calculated numbers, notes word for word (`prompt.py`)
5. **LLM call**: OpenAI, low temperature, JSON reply (`llm.py`)
6. **Parsing**: tolerant JSON reader with a fallback (`checks.py`)
7. **Checks and confidence**: drops invented categories, removes evidence that isn't in the notes, overrides wrong price/volume calls, caps confidence by evidence (`checks.py`)
8. **Database**: every report saved in SQLite (`db.py`)
9. **Report page**: cards, tables and confidence bars, no raw JSON
10. **Admin dashboard**: usage, failure-mode counters, cost, errors (`admin.py`)

## Running it

Add these in Replit under **Secrets**:

| Name | Needed? | What it does |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Your OpenAI key |
| `OPENAI_MODEL` | No | Defaults to `gpt-4o-mini` |
| `ADMIN_PASSWORD` | No | Locks the admin page. If not set, the page is open |
| `SESSION_SECRET` | No | Any long random text |

Then press Run. Locally: `pip install -r requirements.txt` and `python main.py`.

## Thresholds

All in `logic.py` so they're easy to change:

- A line is material if it moved 5% or more **and** by at least 0.5% of total forecast
- A swing of 50% or more is flagged as an anomaly
- Key drivers are the lines that together explain about 80% of the movement
- Confidence caps: 90 with units, 75 with notes only, 35 with neither
