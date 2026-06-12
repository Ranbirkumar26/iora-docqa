"""Memory capture heuristic. Pure (no DB)."""
from app.core.memory import detect_remember


def test_remember_prefix():
    assert detect_remember("remember my name is Ranbir") == "my name is Ranbir"
    assert detect_remember("remember that I like tea.") == "I like tea"
    assert detect_remember("Remember the launch is in June") == "the launch is in June"


def test_other_triggers():
    assert detect_remember("note that the budget is 5 lakh") == "the budget is 5 lakh"
    assert detect_remember("don't forget I sit in Bangalore") == "I sit in Bangalore"
    assert detect_remember("keep in mind that I prefer short answers") == (
        "I prefer short answers"
    )


def test_identity_statements():
    assert detect_remember("my name is Bob") == "my name is Bob"
    assert detect_remember("I work in sales") == "I work in sales"


def test_non_remember_returns_none():
    assert detect_remember("what is my name?") is None
    assert detect_remember("which region had the most revenue?") is None
    assert detect_remember("summarize the documents") is None
