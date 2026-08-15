from __future__ import annotations

import unittest

from app.services.assessment_catalog import (
    ASSESSMENT_BY_CODE,
    ASSESSMENTS,
    ERA_NEEDS,
    ERA_RIASEC,
    GSE,
    IPIP_BIG5,
    STRENGTHS_DEFINITION,
    WHO5,
)
from app.services.assessment_service import score_scale


class AssessmentCatalogTests(unittest.TestCase):
    def test_ten_user_facing_research_directions_are_present(self) -> None:
        self.assertEqual(len(ASSESSMENTS), 9)
        self.assertEqual(len(ASSESSMENT_BY_CODE), 9)
        self.assertEqual(STRENGTHS_DEFINITION["code"], "STRENGTHS_SYNTHESIS")

    def test_every_real_assessment_has_a_version_questions_and_scoring(self) -> None:
        for item in ASSESSMENTS:
            with self.subTest(item=item["code"]):
                self.assertEqual(item["license_status"], "approved")
                self.assertTrue(item["version"])
                self.assertGreater(len(item["questions"]), 0)
                self.assertGreater(len(item["scoring"]), 0)
                self.assertGreater(len(item["response_scale"]), 1)

    def test_official_and_original_instruments_are_not_mislabelled(self) -> None:
        self.assertIn("World Health Organization", WHO5["source"])
        self.assertIn("General Self-Efficacy", GSE["methodology"])
        self.assertEqual(IPIP_BIG5["license"], "Public domain")
        self.assertIn("ERA Russian RIASEC", ERA_RIASEC["methodology"])
        self.assertIn(
            "not presented as an official O*NET translation",
            ERA_RIASEC["translation_source"],
        )
        self.assertIn("ERA Basic Needs Snapshot", ERA_NEEDS["methodology"])
        self.assertIn("Not presented as BPNSFS/BPNSS", ERA_NEEDS["translation_source"])

    def test_who5_uses_five_items_and_zero_to_five_response_values(self) -> None:
        self.assertEqual(len(WHO5["questions"]), 5)
        self.assertEqual(
            {option["value"] for option in WHO5["response_scale"]},
            {0, 1, 2, 3, 4, 5},
        )

    def test_big_five_has_fifty_items_and_ten_per_scale(self) -> None:
        self.assertEqual(len(IPIP_BIG5["questions"]), 50)
        counts: dict[str, int] = {}
        for question in IPIP_BIG5["questions"]:
            counts[question["scale"]] = counts.get(question["scale"], 0) + 1
        self.assertEqual(
            counts,
            {
                "extraversion": 10,
                "agreeableness": 10,
                "conscientiousness": 10,
                "emotional_stability": 10,
                "intellect": 10,
            },
        )


class AssessmentScoringTests(unittest.TestCase):
    def test_who5_minimum_and_maximum_are_zero_and_one_hundred(self) -> None:
        rule = {"method": "sum_times", "factor": 4, "min": 0, "max": 100}
        self.assertEqual(score_scale([(0, False)] * 5, rule), (0.0, 0.0))
        self.assertEqual(score_scale([(5, False)] * 5, rule), (100.0, 100.0))

    def test_gse_sum_maps_ten_to_zero_and_forty_to_one_hundred(self) -> None:
        rule = {"method": "sum", "min": 10, "max": 40}
        self.assertEqual(score_scale([(1, False)] * 10, rule), (10.0, 0.0))
        self.assertEqual(score_scale([(4, False)] * 10, rule), (40.0, 100.0))

    def test_reverse_scoring_flips_one_to_five(self) -> None:
        rule = {"method": "mean_reverse", "min": 1, "max": 5}
        raw, normalized = score_scale([(1, True), (5, False)], rule)
        self.assertEqual(raw, 5.0)
        self.assertEqual(normalized, 100.0)

    def test_plain_mean_does_not_reverse(self) -> None:
        rule = {"method": "mean", "min": 1, "max": 5}
        raw, normalized = score_scale([(1, False), (5, False)], rule)
        self.assertEqual(raw, 3.0)
        self.assertEqual(normalized, 50.0)


if __name__ == "__main__":
    unittest.main()
