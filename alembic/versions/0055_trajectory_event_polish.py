"""Polish Trajectory event in production."""
from alembic import op
import sqlalchemy as sa

revision = "0055_trajectory_event_polish"
down_revision = "0054_trajectory_discoveries"
branch_labels = None
depends_on = None

TITLE = "Международный научно-просветительский форум «Траектория открытий»"


def upgrade():
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE events
        SET title = :title,
            description = :description,
            additional_info = :additional_info,
            status = 'registration_open',
            points_for_visit = 150,
            location = 'Дом Москвы в Ереване',
            event_time = TIME '10:00:00',
            updated_at = CURRENT_TIMESTAMP
        WHERE event_date = DATE '2026-10-31'
          AND title = CAST(:title AS VARCHAR)
    """), {
        "title": TITLE,
        "description": """Образовательная программа для молодых соотечественников.\n\n🕙 ПРОГРАММА\n10:00–10:15 — Открытие\n10:15–11:30 — Лекция «Как развивать критическое мышление в эпоху ИИ: практические инструменты для молодёжи»\n11:30–12:00 — Кофе-брейк\n12:00–13:15 — Мастер-класс «Историческая правда и фейки: как работать с источниками при изучении российской истории»\n13:15–13:30 — Завершение\n\n🎓 Все участники получат сертификаты.\n⭐ За подтверждённое посещение — 150 баллов ЭРА.""",
        "additional_info": "Регистрация проходит через ЭРА. Для участия также необходимо присоединиться к чату мероприятия: https://t.me/+Vz588wqkyt82ZTRi",
    })


def downgrade():
    pass
