from __future__ import annotations
import pytest
from app.services.development_service import RECOMMENDATIONS, normalize_state_answers, pick_recommendation, vector_index

def test_state_snapshot_minimum_and_maximum()->None:
    low=normalize_state_answers({"energy":0,"agency":0,"autonomy":0,"connection":0,"direction":0});high=normalize_state_answers({"energy":4,"agency":4,"autonomy":4,"connection":4,"direction":4});assert vector_index(low)==0;assert vector_index(high)==100

def test_state_index_is_only_state_dimensions()->None:
    assert vector_index({"energy":50,"agency":75,"autonomy":100,"connection":25,"direction":50})==60

def test_invalid_state_answer_is_rejected()->None:
    with pytest.raises(ValueError,match="invalid_energy"):normalize_state_answers({"energy":5,"agency":2,"autonomy":2,"connection":2,"direction":2})

def test_low_energy_prioritizes_recovery()->None:
    tag,_=pick_recommendation({"energy":25,"agency":75,"autonomy":75,"connection":75,"direction":75});assert tag=="RECOVER"

def test_unfinished_goal_is_made_smaller_when_energy_is_not_low()->None:
    tag,_=pick_recommendation({"energy":65,"agency":70,"autonomy":70,"connection":70,"direction":70},previous_goal_unfinished=True);assert tag=="START_SMALL"

def test_semantic_cooldown_skips_repeated_family()->None:
    tag,_=pick_recommendation({"energy":25,"agency":30,"autonomy":70,"connection":70,"direction":70},blocked_tags={"RECOVER"});assert tag=="START_SMALL"

def test_recommendations_never_use_diagnostic_labels()->None:
    forbidden=("депресс","расстройство","выгорание","нестабил");rendered=" ".join(f"{i['title']} {i['insight']} {i['experiment']}".lower() for i in RECOMMENDATIONS.values());assert not any(w in rendered for w in forbidden)
