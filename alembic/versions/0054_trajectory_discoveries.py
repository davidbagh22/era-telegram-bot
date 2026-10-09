"""Create Trajectory of Discoveries event for 31 October 2026."""
from alembic import op
import sqlalchemy as sa

revision = "0054_trajectory_discoveries"
down_revision = "0053_restore_era_admin"
branch_labels = None
depends_on = None

TITLE = "Международный научно-просветительский форум «Траектория открытий»"

def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("""
        INSERT INTO events (
            title, description, event_date, event_time, location, format,
            responsible_id, participant_limit, access_type, needs_volunteers,
            points_for_visit, selfie_required, additional_info, status,
            created_by, approved_by, scoring_preset, scoring_metrics,
            created_at, updated_at
        )
        SELECT
            :title,
            :description,
            DATE '2026-10-31', TIME '10:00:00',
            'Дом Москвы в Ереване', 'Образовательная программа',
            10, NULL, 'all', FALSE, 150, FALSE,
            :additional_info, 'registration_open',
            10, 10, 'standard', CAST('[]' AS json),
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE EXISTS (SELECT 1 FROM users WHERE id = 10)
          AND NOT EXISTS (
            SELECT 1 FROM events WHERE title = CAST(:title AS VARCHAR) AND event_date = DATE '2026-10-31'
        )
    """), {
        "title": TITLE,
        "description": """10:00–10:15 — Открытие мероприятия
10:15–11:30 — Лекция «Как развивать критическое мышление в эпоху ИИ: практические инструменты для молодёжи»
11:30–12:00 — Кофе-брейк
12:00–13:15 — Мастер-класс «Историческая правда и фейки: как работать с источниками при изучении российской истории»
13:15–13:30 — Завершение мероприятия

Все участники получат сертификаты.""",
        "additional_info": "Для регистрации необходимо зарегистрироваться на мероприятие в ЭРА и присоединиться к общему чату: https://t.me/+Q6MzTrnR21dmZjgy",
    })

def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM events WHERE title=CAST(:title AS VARCHAR) AND event_date=DATE '2026-10-31'"), {"title": TITLE})
