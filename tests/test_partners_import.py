from app.database.partners import Partner
from app.handlers.participant import partners
from app.handlers.admin import partners_admin


def test_partner_imports():
    assert Partner.__tablename__ == "partners"
    assert partners.router.name == "participant_partners"
    assert partners_admin.router.name == "admin_partners"
