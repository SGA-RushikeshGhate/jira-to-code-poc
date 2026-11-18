"""Unit tests for the promotion agent's pure helpers."""
import pytest

from promote import (
    STAGES,
    agent_branch_name,
    mentions_issue,
    resolve_target_env,
    validate_issue_key,
)


@pytest.mark.parametrize(
    "status, expected",
    [("Ready for UAT", "uat"), ("ready for prod", "prod"), ("In Progress", None), ("", None)],
)
def test_resolve_target_env(status, expected):
    assert resolve_target_env(status) == expected


def test_stage_branch_mapping():
    assert (STAGES["uat"]["source_branch"], STAGES["uat"]["target_branch"]) == ("dev", "uat")
    assert (STAGES["prod"]["source_branch"], STAGES["prod"]["target_branch"]) == ("uat", "main")


def test_validate_issue_key():
    assert validate_issue_key(" scrum-5 ") == "SCRUM-5"
    for bad in ["SCRUM", "5", "SCRUM-5; rm -rf /", ""]:
        with pytest.raises(ValueError):
            validate_issue_key(bad)


def test_mentions_issue_is_exact():
    assert mentions_issue("SCRUM-5", "SCRUM-5: add feature", "x")
    assert mentions_issue("SCRUM-5", "Promote", "feat/SCRUM-5")
    assert not mentions_issue("SCRUM-5", "SCRUM-50: other", "feat/SCRUM-50")


def test_agent_branch_name():
    assert agent_branch_name("SCRUM-5", "uat") == "agent/SCRUM-5-uat"
