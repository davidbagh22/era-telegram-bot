from app.commission_bot_engagement import (
    SURVEY_TEMPLATES,
    country_region,
    survey_template_for_month,
    target_matches_segment,
    user_matches_segment,
)


def test_ten_distinct_survey_templates_and_rotation():
    assert len(SURVEY_TEMPLATES) == 10
    assert len({x["key"] for x in SURVEY_TEMPLATES}) == 10
    assert all(len(x["questions"]) == 4 for x in SURVEY_TEMPLATES)
    assert survey_template_for_month(2026, 10)["key"] == "belonging"
    assert survey_template_for_month(2026, 11)["key"] == "communication"
    assert survey_template_for_month(2027, 8)["key"] == "belonging"


def test_country_region_catalog_examples():
    assert country_region("AM") == "caucasus"
    assert country_region("RU") == "russia"
    assert country_region("FR") == "europe"
    assert country_region("KZ") == "central_asia"
    assert country_region("US") == "north_america"
    assert country_region(None) is None


def test_user_segment_filters_are_conjunctive_across_dimensions():
    user = {
        "country_code": "AM",
        "age": 24,
        "participant_status": "student",
        "interests": ["international", "leadership"],
        "tags": ["activist"],
        "is_active": True,
    }
    segment = {
        "regions": ["caucasus"],
        "age_buckets": ["18_25"],
        "statuses": ["student"],
        "interests": ["international"],
        "tags": ["activist"],
        "active_only": True,
    }
    assert user_matches_segment(user, segment)
    assert not user_matches_segment(user, {**segment, "countries": ["GE"]})
    assert not user_matches_segment(user, {**segment, "age_buckets": ["26_35"]})
    assert not user_matches_segment({**user, "is_active": False}, segment)


def test_global_target_does_not_leak_into_narrow_campaign():
    global_target = {
        "geography_scope": "global",
        "country_code": None,
        "region_code": None,
    }
    armenia_target = {
        "geography_scope": "country",
        "country_code": "AM",
        "region_code": "caucasus",
    }
    caucasus_target = {
        "geography_scope": "region",
        "country_code": None,
        "region_code": "caucasus",
    }
    assert target_matches_segment(global_target, {})
    assert not target_matches_segment(global_target, {"countries": ["AM"]})
    assert target_matches_segment(armenia_target, {"countries": ["AM"]})
    assert not target_matches_segment(armenia_target, {"countries": ["GE"]})
    assert target_matches_segment(armenia_target, {"regions": ["caucasus"]})
    assert target_matches_segment(caucasus_target, {"regions": ["caucasus"]})
    assert not target_matches_segment(caucasus_target, {"countries": ["AM"]})
