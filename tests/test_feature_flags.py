import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.feature_flags import Feature, feature_enabled, visible_features


def settings(**overrides) -> Settings:
    return Settings(bot_token="1234567890:test", **overrides)


def test_feature_all_is_visible_to_every_participant() -> None:
    cfg = settings(feature_vector="all")

    assert feature_enabled(cfg, Feature.VECTOR, telegram_id=101) is True


def test_feature_off_is_hidden_even_from_tester() -> None:
    cfg = settings(feature_vector="off", feature_tester_ids=[101])

    assert feature_enabled(cfg, Feature.VECTOR, telegram_id=101) is False


def test_testers_mode_uses_explicit_tester_ids_only() -> None:
    cfg = settings(feature_vector="testers", feature_tester_ids=[101, 202])

    assert feature_enabled(cfg, Feature.VECTOR, telegram_id=101) is True
    assert feature_enabled(cfg, Feature.VECTOR, telegram_id=303) is False
    assert feature_enabled(cfg, Feature.VECTOR, telegram_id=None) is False


def test_visible_features_returns_all_known_feature_keys() -> None:
    cfg = settings(feature_auctions="off", feature_vector="all")

    flags = visible_features(cfg, telegram_id=101)

    assert set(flags) == {feature.value for feature in Feature}
    assert flags[Feature.AUCTIONS.value] is False
    assert flags[Feature.VECTOR.value] is True


def test_invalid_feature_mode_fails_configuration() -> None:
    with pytest.raises(ValidationError):
        settings(feature_vector="sometimes")
