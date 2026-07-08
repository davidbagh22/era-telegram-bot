import unittest


class Pr3CleanImportsTests(unittest.TestCase):
    def test_partner_models_import(self) -> None:
        from app.database.partners import Partner, PartnerInitiative, PartnerTask

        self.assertEqual(Partner.__tablename__, "partners")
        self.assertEqual(PartnerInitiative.__tablename__, "partner_initiatives")
        self.assertEqual(PartnerTask.__tablename__, "partner_tasks")

    def test_pr3_routers_import(self) -> None:
        from app.handlers.admin import partners_admin
        from app.handlers.participant import partners, point_transfer
        from app.states.point_transfer import PointTransferStates

        self.assertEqual(partners.router.name, "participant_partners")
        self.assertEqual(point_transfer.router.name, "point_transfer")
        self.assertEqual(partners_admin.router.name, "admin_partners")
        self.assertTrue(PointTransferStates.recipient.state)


if __name__ == "__main__":
    unittest.main()
