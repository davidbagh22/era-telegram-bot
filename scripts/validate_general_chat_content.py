#!/usr/bin/env python3
"""Strict editorial/content-pack validation for the ERA general chat ritual."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "content" / "general_chat"
BANNED = (
    "ты обязан",
    "хватит лениться",
    "победители никогда не сдаются",
    "стань лучшей версией себя",
    "ты можешь всё",
    "зона комфорта",
)
EXPECTED_HOLIDAYS = {
    "01-01",
    "02-19",
    "02-21",
    "03-08",
    "03-20",
    "04-07",
    "04-23",
    "05-09",
    "06-06",
    "07-30",
    "08-12",
    "09-01",
    "10-05",
    "12-05",
    "12-31",
}
TAG_RE = re.compile(r"<[^>]+>")
WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")


def load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def fail(message: str) -> None:
    raise AssertionError(message)


def normalize(text: str) -> str:
    plain = TAG_RE.sub(" ", text).lower().replace("ё", "е")
    return " ".join(WORD_RE.findall(plain))


def words(text: str) -> list[str]:
    return WORD_RE.findall(TAG_RE.sub(" ", text))


def tokens(text: str) -> set[str]:
    return set(normalize(text).split())


def check_html(text: str, content_id: str) -> None:
    tags = TAG_RE.findall(text)
    unknown = [tag for tag in tags if tag not in {"<b>", "</b>"}]
    if unknown:
        fail(f"{content_id}: unsupported HTML tags {unknown}")
    if text.count("<b>") != text.count("</b>"):
        fail(f"{content_id}: unbalanced <b> tags")


def render_quote(key: str, slot: str, spec: list[int], fragments, themes) -> str:
    family, a, b, c, theme_thread = spec
    block = fragments[slot]
    if family == 0:
        first = f"Если сегодня {block['conditions'][a]}, {block['responses'][b]}."
        last = block["actions" if slot == "morning" else "end"][c]
    elif family == 1:
        first = f"Сегодня {block['today'][a]}. {block['follow'][b]}"
        last = block["actions" if slot == "morning" else "end"][c]
    elif family == 2:
        first = f"Иногда {block['sometimes'][a]}. {block['insight'][b]}"
        last = block["actions" if slot == "morning" else "end"][c]
    else:
        fail(f"{key}/{slot}: unknown quote family {family}")
    text = f"{first} {last}"
    if theme_thread:
        practice = themes[int(key[:2])]["practice"]
        if slot == "morning":
            text += f" В теме этого месяца попробуй {practice}."
        else:
            text += f" Если нужен ориентир на завтра, продолжай {practice}."
    return text


def assert_unique_texts(named_texts: list[tuple[str, str]]) -> None:
    normalized: dict[str, str] = {}
    for content_id, text in named_texts:
        value = normalize(text)
        if not value:
            fail(f"{content_id}: empty normalized text")
        if value in normalized:
            fail(f"normalized duplicate: {normalized[value]} == {content_id}")
        normalized[value] = content_id


def assert_not_too_similar(named_texts: list[tuple[str, str]]) -> None:
    tokenized = [(content_id, tokens(text)) for content_id, text in named_texts]
    for index, (left_id, left) in enumerate(tokenized):
        for right_id, right in tokenized[index + 1 :]:
            union = left | right
            score = len(left & right) / len(union) if union else 1.0
            if score >= 0.84:
                fail(f"too similar ({score:.2f}): {left_id} / {right_id}")


def main() -> int:
    fragments = load("quote_fragments.json")
    plan = load("quote_plan.json")
    themes_payload = load("monthly_themes.json")
    holidays_payload = load("holidays.json")
    challenge_parts = [
        load("weekly_challenges_01_26.json"),
        load("weekly_challenges_27_52.json"),
    ]
    challenges = challenge_parts[0]["items"] + challenge_parts[1]["items"]
    themes = {int(row["month"]): row for row in themes_payload["items"]}

    if plan.get("count") != 365 or len(plan.get("plans", [])) != 365:
        fail("quote plan must contain exactly 365 days")
    expected_dates: list[str] = []
    cursor = date(2025, 1, 1)
    while cursor.year == 2025:
        expected_dates.append(cursor.strftime("%m-%d"))
        cursor += timedelta(days=1)
    actual_dates = [row[0] for row in plan["plans"]]
    if actual_dates != expected_dates:
        fail("quote plan dates must be exactly Jan 1 through Dec 31 in order")

    morning: list[tuple[str, str]] = []
    evening: list[tuple[str, str]] = []
    for key, morning_spec, evening_spec in plan["plans"]:
        morning.append(
            (f"morning-{key.replace('-', '')}", render_quote(key, "morning", morning_spec, fragments, themes))
        )
        evening.append(
            (f"evening-{key.replace('-', '')}", render_quote(key, "evening", evening_spec, fragments, themes))
        )
    if len({text for _, text in morning}) != 365:
        fail("morning quotes are not all unique")
    if len({text for _, text in evening}) != 365:
        fail("evening quotes are not all unique")

    if len(themes) != 12 or set(themes) != set(range(1, 13)):
        fail("monthly themes must contain months 1..12 exactly once")
    for month, row in themes.items():
        count = len(words(row["text"]))
        if not 115 <= count <= 230:
            fail(f"theme-{month:02d}: expected approximately 130-220 words, got {count}")
        if not row.get("practice", "").strip():
            fail(f"theme-{month:02d}: missing practice")
        check_html(row["text"], row["id"])

    if holidays_payload.get("count") != 15 or len(holidays_payload["items"]) != 15:
        fail("holiday calendar must contain exactly 15 base dates")
    holiday_dates = {row["date_key"] for row in holidays_payload["items"]}
    if holiday_dates != EXPECTED_HOLIDAYS:
        fail("base holiday calendar differs from editorial specification")
    for row in holidays_payload["items"]:
        check_html(row["text"], row["id"])

    if len(challenges) != 52:
        fail(f"weekly challenges must contain exactly 52 items, got {len(challenges)}")
    challenge_dates: set[str] = set()
    for row in challenges:
        challenge_day = date.fromisoformat(row["date"])
        if challenge_day.weekday() != 6:
            fail(f"{row['id']}: challenge date is not Sunday")
        if row["date"] in challenge_dates:
            fail(f"{row['id']}: duplicate challenge date")
        challenge_dates.add(row["date"])
        if int(row["month"]) != challenge_day.month:
            fail(f"{row['id']}: challenge month does not match its Sunday")
        count = len(words(row["text"]))
        if not 70 <= count <= 110:
            fail(f"{row['id']}: expected 70-110 words, got {count}")
        check_html(row["text"], row["id"])

    all_items = (
        morning
        + evening
        + [(row["id"], row["text"]) for row in challenges]
        + [(row["id"], row["text"]) for row in themes_payload["items"]]
        + [(row["id"], row["text"]) for row in holidays_payload["items"]]
    )
    ids = [content_id for content_id, _ in all_items]
    if len(ids) != len(set(ids)):
        fail("content IDs must be globally unique")
    for content_id, text in all_items:
        if not text.strip():
            fail(f"{content_id}: empty text")
        if len(text) > 4096:
            fail(f"{content_id}: exceeds Telegram 4096-character message limit")
        lowered = normalize(text)
        for phrase in BANNED:
            if normalize(phrase) in lowered:
                fail(f"{content_id}: banned phrase '{phrase}'")

    quote_items = morning + evening
    assert_unique_texts(quote_items)
    assert_not_too_similar(quote_items)
    first_sentences = Counter(
        re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip().lower()
        for _, text in quote_items
    )
    repeated = [(sentence, count) for sentence, count in first_sentences.items() if count > 8]
    if repeated:
        fail(f"quote openings repeat too often: {repeated[:3]}")

    # Architecture exposes exactly two editorial slots per date. Replacement
    # priority can change the type in a slot, never add a third slot.
    for key in expected_dates:
        if len({("09:00", "morning"), ("18:00", "evening")}) != 2:
            fail(f"{key}: more than two automated editorial slots")

    print("general chat content validation passed")
    print("365 morning")
    print("365 evening")
    print("52 challenges")
    print("12 themes")
    print("15 holidays")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, IndexError, TypeError, ValueError) as exc:
        print(f"general chat content validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
