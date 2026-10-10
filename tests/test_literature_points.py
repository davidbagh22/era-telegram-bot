"""Regression tests for the ERA literature automatic points integration."""
from pathlib import Path


def test_literature_points_use_durable_idempotency():
    source = Path('app/services/book_club_service.py').read_text()
    assert "make_idempotency_key('literature', 'task', user.id, number)" in source
    assert "points=5" in source
    assert "if kind == 'task':" in source


def test_law_title_is_labeled_not_fabricated_body_quote():
    from app.content.literature_issues import render_issue
    text = render_issue(1)
    assert 'Из книги · название закона' in text
    assert 'Роберт Грин' in text
    assert 'авторский разбор ЭРА' in text
