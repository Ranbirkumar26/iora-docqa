"""Decision-support intent detection. Pure regex; no LLM/network."""
from app.core.decision import looks_decision_support
from app.core.structured import looks_quantitative


def test_detects_recommendation_questions():
    assert looks_decision_support("What should we prioritize next?")
    assert looks_decision_support("Recommend the best next action from this survey")
    assert looks_decision_support("How can we improve onboarding?")
    assert looks_decision_support("What risks should we consider?")


def test_plain_factual_questions_stay_out_of_decision_mode():
    assert not looks_decision_support("Which region had the most revenue?")
    assert not looks_decision_support("How many users mentioned pricing?")
    assert not looks_decision_support("What is the average NPS score?")


def test_quantitative_can_still_win_when_both_match():
    question = "How many users should we follow up with?"
    assert looks_quantitative(question)
    assert looks_decision_support(question)
