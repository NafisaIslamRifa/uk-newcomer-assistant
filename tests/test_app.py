"""Streamlit UI tests with a fake agent (no LLM, no MCP server)."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

import app.runner
from app import ui_helpers as ui


class FakeRunner:
    asked = []

    def __init__(self):
        pass

    def new_chat(self, profile):
        return {"profile": profile}

    def ask(self, chat, question):
        FakeRunner.asked.append((chat["profile"], question))
        return SimpleNamespace(
            answer="Full-time students don't pay council tax "
                   "([Council Tax](https://www.gov.uk/council-tax)).",
            sources=[{"title": "Council Tax", "section": "Discounts for full-time students",
                      "url": "https://www.gov.uk/council-tax", "last_updated": "2025-02-05"}],
            trace=[{"step": 1, "tool": "search_uk_guidance",
                    "args": {"query": "students council tax", "category": "council_tax"},
                    "error": False}],
            guardrails={"high_risk": False, "unsupported_urls": [], "referral_added": False},
            seconds=1.2,
        )


@pytest.fixture
def at(monkeypatch):
    monkeypatch.setattr(app.runner, "AgentRunner", FakeRunner)
    FakeRunner.asked = []
    t = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"), default_timeout=30)
    t.run()
    return t


def test_page_loads_with_quick_questions(at):
    assert not at.exception
    labels = [b.label for b in at.button]
    assert "Council tax" in labels and "New conversation" in labels


def test_chat_round_trip_shows_answer_sources_and_trace(at):
    at.chat_input[0].set_value("Do students pay council tax?").run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Full-time students don't pay council tax" in text
    assert any("Sources (1)" in e.label for e in at.expander)
    assert any("Steps taken" in e.label for e in at.expander)


def test_profile_is_passed_to_agent(at):
    at.selectbox[0].set_value("Student")
    at.text_input[0].set_value("ig11 7lu")
    at.chat_input[0].set_value("Nearest GP?").run()
    profile, _ = FakeRunner.asked[-1]
    assert profile == {"visa_type": "Student", "postcode": "IG11 7LU"}


def test_quick_question_button(at):
    next(b for b in at.button if b.label == "Council tax").click().run()
    assert FakeRunner.asked[-1][1].startswith("Who has to pay council tax")


def test_helpers():
    assert ui.build_profile("Prefer not to say", " ") == {"visa_type": None, "postcode": None}
    assert ui.nice_date("2025-02-05") == "5 Feb 2025"
    line = ui.describe_tool_call({"tool": "find_nearby_services",
                                  "args": {"service_type": "post_office", "postcode": "E1 6AN"}})
    assert "post office" in line and "E1 6AN" in line
