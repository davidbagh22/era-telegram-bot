from app.database.partners import Partner, PartnerInitiative, PartnerTask
from app.handlers.admin import partners_admin
from app.handlers.participant import partners, point_transfer
from app.states.point_transfer import PointTransferStates


def test_partner_models_import():
    assert Partner.__tablename__ == "partners"
    assert PartnerInitiative.__tablename__ == "partner_initiatives"
    assert PartnerTask.__tablename__ == "partner_tasks"


def test_pr3_routers_import():
    assert partners.router.name == "participant_partners"
    assert point_transfer.router.name == "point_transfer"
    assert partners_admin.router.name == "admin_partners"
    assert PointTransferStates.recipient.state
