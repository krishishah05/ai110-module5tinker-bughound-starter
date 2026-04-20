# 🐶 BugHound

BugHound is an agentic debugging assistant. It analyzes a Python code snippet, proposes a targeted fix, runs reliability checks on that fix, and decides whether the change is safe to apply automatically or should be deferred to a human reviewer.

---

## What BugHound Does

Given a short Python snippet, BugHound runs a five-step agentic loop:

1. **PLAN** — Logs intent and sets up the workflow
2. **ANALYZE** — Detects issues using heuristics or Gemini (LLM)
3. **ACT** — Proposes a fix using heuristics or Gemini
4. **TEST** — Scores the fix for risk using `reliability/risk_assessor.py`
5. **REFLECT** — Decides whether to recommend auto-fix or require human review

---

## Modes

| Mode | Requires API key | Analyzer | Fixer |
|---|---|---|---|
| Heuristic only | No | Pattern rules | Regex substitutions |
| Gemini | Yes | Gemini LLM | Gemini LLM |

In both modes, the risk assessment and auto-fix decision use the same local rules.

---

## Reliability Features

- **LLM fallback:** If Gemini returns non-JSON or malformed output, the agent automatically falls back to heuristics and logs the reason.
- **Empty-message guardrail:** If most issues returned by the LLM have empty `msg` fields, the response is rejected and heuristics are used instead.
- **Large-diff penalty:** Fixes that rewrite more than 50% of the original lines are penalized in the risk score and flagged as potential over-editing.
- **Strict auto-fix policy:** Auto-fix requires both a low risk score and fewer than 30% of lines changed — a large rewrite is blocked even if the risk score looks clean.

---

## Setup

### 1. Create a virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# or
.venv\Scripts\activate      # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Running in Offline (Heuristic) Mode

No API key required.

```bash
streamlit run bughound_app.py
```

In the sidebar, select **Model mode: Heuristic only (no API)**.

Heuristic mode detects three patterns:
- `print(` statements → Code Quality / Low
- Bare `except:` blocks → Reliability / High
- `TODO` comments → Maintainability / Medium

---

## Running with Gemini

### 1. Set up your API key

```bash
cp .env.example .env
```

Edit `.env`:

```
GEMINI_API_KEY=your_real_key_here
```

Get a key at [aistudio.google.com/app/apikeys](https://aistudio.google.com/app/apikeys).

### 2. Run the app

```bash
streamlit run bughound_app.py
```

Select **Model mode: Gemini (requires API key)** in the sidebar.

> Note: The Gemini Free Tier allows ~20 requests per day. Use Heuristic mode for initial exploration to preserve your quota.

---

## Running Tests

```bash
pytest
```

12 tests covering:

- Risk scoring and guardrails (including large-diff signal and auto-fix policy)
- Heuristic fallback when LLM returns invalid or empty output
- Agent workflow shape in offline mode
- Bare except correctly blocks auto-fix via risk score

---

## Project Structure

```
bughound_app.py          — Streamlit UI
bughound_agent.py        — Agentic workflow (plan → analyze → act → test → reflect)
llm_client.py            — Gemini and MockClient wrappers
reliability/
  risk_assessor.py       — Risk scoring and auto-fix guardrails
prompts/
  analyzer_system.txt    — System prompt for issue detection
  analyzer_user.txt      — User prompt template for analysis
  fixer_system.txt       — System prompt for fix generation
  fixer_user.txt         — User prompt template for fixing
sample_code/             — Sample Python snippets to test with
tests/                   — pytest test suite
model_card.md            — Reflection on system behavior and failure modes
```
