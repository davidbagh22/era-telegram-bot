import unittest


class Pr3CleanImportsTests(unittest.TestCase):
    def test_partner_models_import(self) -> None:
        from app.database.partners import Partner, PartnerInitiative, PartnerTask

        self.assertEqual(Partner.__tablename__, "partners")
        self.assertEqual(PartnerInitiative.__tablename__, "partner_initiatives")
        self.assertEqual(PartnerTask.__tablename__, "partner_tasks")

    def test_pr3_states_import(self) -> None:
        from app.states.point_transfer import PointTransferStates

        self.assertTrue(PointTransferStates.recipient.state)


if __name__ == "__main__":
    unittest.main()
