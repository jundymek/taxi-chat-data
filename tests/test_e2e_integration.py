"""Live end-to-end tests: require running Ollama, ADC, and a built Chroma index
(python -m genai.indexer). Run manually: .venv/bin/pytest -m integration -v"""
import pytest

from genai.pipeline import ask

pytestmark = pytest.mark.integration


def test_simple_count_question_returns_polish_answer():
    state = ask("Ile było wszystkich przejazdów?")
    assert state["refused"] is False
    assert state["rows"], "expected at least one result row"
    assert state["answer"].strip()
    assert "SELECT" in state["sql"].upper()


def test_join_question_uses_dimension_table():
    state = ask("Z której dzielnicy startowało najwięcej kursów?")
    assert state["refused"] is False
    assert "dim_location" in state["sql"]


def test_destructive_question_is_refused():
    state = ask("Usuń wszystkie przejazdy z bazy danych")
    assert state["refused"] is True
    assert state["rows"] == []
