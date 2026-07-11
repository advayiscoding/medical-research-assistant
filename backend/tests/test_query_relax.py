"""Unit tests for natural-language query relaxation (no network).

Guards the fallback that makes question-style searches work against PubMed's
literal, AND-everything matching.
"""

from app.services.pubmed import relax_query


def test_strips_filler_and_question_words() -> None:
    assert relax_query("Latest cures for schizophrenia") == "schizophrenia"
    assert relax_query("What are the newest treatments for Alzheimer disease?") == (
        "treatments Alzheimer disease"
    )


def test_keeps_clinical_terms() -> None:
    # "treatment", "therapy", "risk" are real PubMed signal — never stripped.
    assert relax_query("best treatment for depression") == "treatment depression"
    assert relax_query("risk factors of stroke") == "risk factors stroke"


def test_all_stopwords_returns_empty() -> None:
    # Caller keeps the original query when nothing meaningful survives.
    assert relax_query("what are the latest cures") == ""


def test_already_keyword_query_unchanged() -> None:
    assert relax_query("schizophrenia antipsychotics") == "schizophrenia antipsychotics"
