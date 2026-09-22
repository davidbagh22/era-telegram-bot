from __future__ import annotations

from enum import StrEnum

from app.config import Settings


class Feature(StrEnum):
    AUCTIONS = "auctions"
    REWARDS = "rewards"
    ERA_PRO = "era_pro"
    SURVEYS = "surveys"
    VECTOR = "vector"
    REFERRALS = "referrals"
    MEDIA = "media"
    ROLE_RECRUITMENT = "role_recruitment"


_FEATURE_ATTR: dict[Feature, str] = {
    Feature.AUCTIONS: "feature_auctions",
    Feature.REWARDS: "feature_rewards",
    Feature.ERA_PRO: "feature_era_pro",
    Feature.SURVEYS: "feature_surveys",
    Feature.VECTOR: "feature_vector",
    Feature.REFERRALS: "feature_referrals",
    Feature.MEDIA: "feature_media",
    Feature.ROLE_RECRUITMENT: "feature_role_recruitment",
}


def feature_mode(settings: Settings, feature: Feature) -> str:
    return str(getattr(settings, _FEATURE_ATTR[feature])).upper()


def feature_enabled(settings: Settings, feature: Feature, telegram_id: int | None = None) -> bool:
    """Return participant visibility for one optional module.

    TESTERS is deliberately independent from admin status. The caller passes a
    Telegram id and only FEATURE_TESTER_IDS grants tester visibility.
    """

    mode = feature_mode(settings, feature)
    if mode == "ALL":
        return True
    if mode == "OFF":
        return False
    return telegram_id is not None and telegram_id in set(settings.feature_tester_ids)


def visible_features(settings: Settings, telegram_id: int | None = None) -> dict[str, bool]:
    return {
        feature.value: feature_enabled(settings, feature, telegram_id)
        for feature in Feature
    }
