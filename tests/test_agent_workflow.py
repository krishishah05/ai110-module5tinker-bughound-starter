from bughound_agent import BugHoundAgent
from llm_client import MockClient


def test_workflow_runs_in_offline_mode_and_returns_shape():
    agent = BugHoundAgent(client=None)  # heuristic-only
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert isinstance(result, dict)
    assert "issues" in result
    assert "fixed_code" in result
    assert "risk" in result
    assert "logs" in result

    assert isinstance(result["issues"], list)
    assert isinstance(result["fixed_code"], str)
    assert isinstance(result["risk"], dict)
    assert isinstance(result["logs"], list)
    assert len(result["logs"]) > 0


def test_offline_mode_detects_print_issue():
    agent = BugHoundAgent(client=None)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert any(issue.get("type") == "Code Quality" for issue in result["issues"])


def test_offline_mode_proposes_logging_fix_for_print():
    agent = BugHoundAgent(client=None)
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    fixed = result["fixed_code"]
    assert "logging" in fixed
    assert "logging.info(" in fixed


def test_mock_client_forces_llm_fallback_to_heuristics_for_analysis():
    # MockClient returns non-JSON for analyzer prompts, so agent should fall back.
    agent = BugHoundAgent(client=MockClient())
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    assert any(issue.get("type") == "Code Quality" for issue in result["issues"])
    # Ensure we logged the fallback path
    assert any("Falling back to heuristics" in entry.get("message", "") for entry in result["logs"])


def test_bare_except_with_high_severity_does_not_autofix():
    # A bare except is a High severity issue which drives risk score below the
    # auto-fix threshold. The agent must recommend human review, not auto-apply.
    agent = BugHoundAgent(client=None)
    code = "def load(path):\n    try:\n        return open(path).read()\n    except:\n        return None\n"
    result = agent.run(code)

    assert result["risk"]["should_autofix"] is False
    assert any(
        "Human review" in entry.get("message", "") or "not safe" in entry.get("message", "")
        for entry in result["logs"]
    )


class _EmptyMsgClient:
    """Returns structurally valid JSON but every issue has an empty msg."""

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if "Return ONLY valid JSON" in system_prompt:
            return '[{"type": "Bug", "severity": "High", "msg": ""}]'
        return "# no fix\n"


def test_llm_issues_with_empty_messages_fall_back_to_heuristics():
    # Guardrail: if the LLM returns issues with mostly empty messages,
    # the agent should reject the output and use heuristics instead.
    agent = BugHoundAgent(client=_EmptyMsgClient())
    code = "def f():\n    print('hi')\n    return True\n"
    result = agent.run(code)

    # Heuristic fallback should have fired and found the Code Quality issue.
    assert any(issue.get("type") == "Code Quality" for issue in result["issues"])
    assert any("empty messages" in entry.get("message", "") for entry in result["logs"])
