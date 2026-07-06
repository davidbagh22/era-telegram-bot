from app.handlers.participant import point_transfer
from app.states.point_transfer import PointTransferStates


def test_point_transfer_imports():
    assert point_transfer.router.name == "point_transfer"
    assert PointTransferStates.recipient.state
