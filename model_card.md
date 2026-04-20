# BugHound Mini Model Card (Reflection)

---

## 1) What is this system?

**Name:** BugHound  
**Purpose:** An agentic debugging assistant that analyzes a Python code snippet, proposes a targeted fix, runs reliability checks on that fix, and decides whether the change is safe to apply automatically or should be deferred to a human reviewer.

**Intended users:** Developers who want a quick, cautious first pass on short Python scripts before committing changes. Also useful as a teaching example for agentic workflow design and AI reliability concepts.

---

## 2) How does it work?

BugHound follows a five-step agentic loop:

1. **PLAN** — The agent logs its intent: scan the code and produce a fix proposal. No AI call is made here; this step exists to make the agent's reasoning auditable.

2. **ANALYZE** — If an LLM client is available, BugHound sends the code to Gemini with a structured prompt asking for a JSON array of issues (type, severity, msg). If the response is not valid JSON, or if most issues have empty messages, it falls back to heuristic rules: bare `except:` → High severity, `print(` → Low severity, `TODO` → Medium severity.

3. **ACT** — If issues were found, BugHound generates a fix. With an LLM client it asks Gemini to rewrite the code minimally while preserving behavior. In heuristic mode it applies regex substitutions: bare excepts become `except Exception as e:`, prints become `logging.info(`.

4. **TEST** — `risk_assessor.py` scores the proposed fix from 0–100 based on issue severity, whether returns were removed, whether the fix is dramatically shorter than the original, and whether more than 50% of lines were rewritten.

5. **REFLECT** — If the risk score is "low" and fewer than 30% of lines changed, the agent recommends auto-fix. Otherwise it flags the change for human review.

**Heuristics vs Gemini:** Heuristics are fast, offline, and deterministic but can only catch the three patterns coded into `_heuristic_analyze`. Gemini detects a wider range of issues including variable shadowing, missing type annotations, and logic smells, but requires an API key and can produce malformed output that the fallback logic must handle.

---

## 3) Inputs and outputs

**Inputs tested:**

- `print_spam.py` — a short function with multiple `print` calls, no error handling
- `flaky_try_except.py` — a file-reader function with a bare `except:` that silently swallows all errors
- `mixed_issues.py` — combines a TODO comment, a print statement, and a bare except inside a division operation
- `cleanish.py` — a well-structured function using `logging` with no obvious issues

**Outputs observed:**

- *Issues detected:* Code Quality (print statements), Reliability (bare except), Maintainability (TODO). Gemini also flagged the missing `f.close()` in `flaky_try_except.py` as a resource leak.
- *Fixes proposed:* Heuristic mode added `import logging` and swapped `print(` → `logging.info(`, and replaced `except:` with `except Exception as e:`. LLM mode rewrote whole functions in some cases, adding docstrings and restructuring control flow.
- *Risk report:* `cleanish.py` scored 95 (low risk, auto-fix allowed). `mixed_issues.py` with a bare except scored 35 (high risk, human review required). `flaky_try_except.py` got penalized both for the bare except severity and for a large-diff rewrite, scoring 30.

---

## 4) Reliability and safety rules

**Rule 1: High-severity issue deducts 40 points from the risk score**

- *What it checks:* Whether any detected issue has `"severity": "High"` — currently triggered by bare `except:` blocks.
- *Why it matters:* A bare except silently catches `KeyboardInterrupt`, `SystemExit`, and memory errors. Fixing it can change program behavior in subtle ways (e.g., an exception that previously caused a clean exit now gets swallowed), so the fix needs human verification.
- *False positive:* Code that uses a bare except intentionally as a final fallback logger (valid in some CLI tools) would be penalized even if the fix is correct.
- *False negative:* An `except Exception:` that still swallows all application errors without logging would not be flagged, since it passes the heuristic pattern check.

**Rule 2: Large-diff signal deducts 25 points when more than 50% of lines changed**

- *What it checks:* Uses `difflib.SequenceMatcher` to count lines that were inserted, deleted, or replaced. If the ratio of changed lines to original lines exceeds 0.5, the score is penalized and auto-fix is blocked.
- *Why it matters:* A fix that rewrites most of the file is much more likely to alter behavior even if it addresses the flagged issue. The original intent of the code is harder to verify in a large diff.
- *False positive:* A file with three short lines where two are changed (67%) would be flagged even if the fix is clearly correct and safe.
- *False negative:* A fix could change 40% of lines (below the threshold) while still introducing a subtle logic error in the one method that matters.

---

## 5) Observed failure modes

**Failure 1 — Missed issue: resource leak in `flaky_try_except.py`**

```python
def load_text_file(path):
    try:
        f = open(path, "r")
        data = f.read()
        f.close()
    except:
        return None
    return data
```

Heuristic mode only flagged the bare `except:`. It did not detect that `f.close()` is never called if `f.read()` raises an exception, leaving a file handle open. This is a real reliability issue that heuristics cannot catch without data-flow analysis. Gemini did flag it as a resource management issue in LLM mode.

**Failure 2 — Over-editing in `mixed_issues.py`**

When run in Gemini mode, the proposed fix for `mixed_issues.py` restructured the entire function: it removed the `TODO` comment, added a docstring, renamed the parameter from `x` to `numerator`, added input type validation, and replaced the bare except with a specific `ZeroDivisionError` handler. The fix was arguably better code, but it changed far more than what the issues required. The large-diff guardrail caught this and set `should_autofix` to `False`, which was the correct outcome — but the user would still need to review a heavily rewritten function rather than a minimal patch.

---

## 6) Heuristic vs Gemini comparison

| Dimension | Heuristic mode | Gemini mode |
|---|---|---|
| Issues found on `print_spam.py` | 1 (print statement) | 2 (print statement + verbose flag could use early return) |
| Issues found on `flaky_try_except.py` | 1 (bare except) | 3 (bare except, resource leak, missing type hint) |
| Issues found on `cleanish.py` | 0 | 0–1 (sometimes flagged the logging level as unnecessarily verbose) |
| Fix style | Minimal regex substitutions, always predictable | Full rewrites, more readable but higher diff ratio |
| Risk scorer agreement | Consistently agreed — heuristic fixes are small and targeted | Occasionally disagreed with my intuition: a "good" Gemini fix would still be blocked because of diff size |

Heuristics were more consistent and easier to predict. Gemini added real value on the resource leak case that heuristics cannot detect. The risk scorer was well-calibrated for heuristic fixes but conservative about Gemini fixes, which was the safer default.

---

## 7) Human-in-the-loop decision

**Scenario:** The user pastes an authentication function that reads from a JWT token or environment-based secret. BugHound detects that the function lacks input validation and proposes a rewrite that changes how the token is checked.

Even if the risk score comes back "low" (the diff is small and no return statements were removed), a change to authentication logic should never be auto-applied. A subtle difference in comparison operator or exception handling could introduce a security bypass.

**Trigger:** Add a keyword scan in `risk_assessor.py`: if any of `["token", "secret", "password", "auth", "credential", "api_key"]` appear in the original code, force `should_autofix = False` and add the reason `"Code appears to involve authentication or credentials — human review required."` This runs before the scoring logic so it can short-circuit the decision entirely.

**Where to implement:** `risk_assessor.py`, as a new rule block after the structural checks. This keeps the policy in the reliability layer rather than scattered across the agent and UI.

**Message to show the user:** `"BugHound detected authentication-related code. Auto-fix is disabled for security-sensitive changes. Review the proposed diff manually before applying."`

---

## 8) Improvement idea

**Improvement: Require the LLM fixer to return a structured diff instead of full rewritten code.**

Currently the fixer prompt asks for the complete rewritten file. This makes the diff hard to trust — the entire file changes, making it difficult to isolate what was actually fixed from what was incidentally reformatted.

A better approach: change the fixer prompt to ask for a list of targeted replacement pairs: `{"original": "<exact lines to replace>", "replacement": "<new lines>"}`. The agent would then apply each replacement surgically using a simple string substitution, producing a minimal, auditable diff.

This would reduce the large-diff penalty in most cases, make the risk scorer more accurate, and give the user a much clearer picture of what changed and why. The change requires updating `propose_fix` to parse and apply the structured replacements, and adding a fallback to full-rewrite mode if parsing fails.
