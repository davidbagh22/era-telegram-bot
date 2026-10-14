"""Literature discussion must stay in a dedicated general-chat forum topic."""
from app.services.general_topics_service import TOPICS


def test_literature_topic_is_registered():
    assert TOPICS['literature'] == 'Литература'


def test_literature_publication_uses_durable_topic_delivery():
    from pathlib import Path
    source = Path('app/services/book_club_service.py').read_text()
    assert "send_general_topic(" in source
    assert "'literature', render_issue(number)" in source
    assert "delivery_key=f'issue:{start_day.isoformat()}:{number}'" in source
