"""Eleven explicit game formats, each with its own scoring and answer rules.

This module is deliberately independent of Telegram so its behavior can be tested.
The Telegram room handler must integrate these mechanics before public release.
"""
from dataclasses import dataclass
from enum import StrEnum


class GameMode(StrEnum):
    SOLO_QUIZ = "solo_quiz"
    TEAM_QUIZ = "team_quiz"
    TRUE_OR_MYTH = "true_or_myth"
    GUESS_COUNTRY = "guess_country"
    CHRONOLOGY = "chronology"
    WORD_CHAIN = "word_chain"
    ASSOCIATIONS = "associations"
    LOGIC = "logic"
    CULTURE = "culture"
    MEMORY = "memory"
    TEAM_DUEL = "team_duel"


@dataclass(frozen=True)
class Challenge:
    mode: GameMode
    prompt: str
    answer: str
    options: tuple[str, ...] = ()
    hints: tuple[str, ...] = ()
    explanation: str = ""


def normalize(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def check_answer(challenge: Challenge, answer: str, *, previous_word: str = "") -> bool:
    """Check a response using the rules of its format."""
    value = normalize(answer)
    expected = normalize(challenge.answer)
    if not value:
        return False
    if challenge.mode == GameMode.WORD_CHAIN:
        if not previous_word:
            return value == expected
        previous = normalize(previous_word).rstrip("ьъы")
        return bool(previous) and value.startswith(previous[-1]) and value == expected
    if challenge.mode == GameMode.CHRONOLOGY:
        return tuple(part.strip() for part in value.split(",")) == tuple(
            part.strip() for part in expected.split(",")
        )
    if challenge.mode == GameMode.MEMORY:
        return value.replace(" ", "") == expected.replace(" ", "")
    return value == expected


def score_answer(challenge: Challenge, answer: str, *, hints_used: int = 0,
                 previous_word: str = "") -> int:
    if not check_answer(challenge, answer, previous_word=previous_word):
        return 0
    if challenge.mode in (GameMode.GUESS_COUNTRY, GameMode.ASSOCIATIONS):
        return max(1, 4 - max(0, hints_used))
    if challenge.mode == GameMode.TEAM_DUEL:
        return 2
    return 1


def validate_challenge(challenge: Challenge) -> None:
    if not challenge.prompt.strip() or not challenge.answer.strip():
        raise ValueError("Prompt and answer are required")
    if challenge.mode in (GameMode.SOLO_QUIZ, GameMode.TEAM_QUIZ,
                          GameMode.TRUE_OR_MYTH, GameMode.CULTURE,
                          GameMode.TEAM_DUEL):
        if len(challenge.options) < 2:
            raise ValueError("Choice-based format needs at least two options")
        if len({normalize(item) for item in challenge.options}) != len(challenge.options):
            raise ValueError("Options must be unique")
        if normalize(challenge.answer) not in {normalize(item) for item in challenge.options}:
            raise ValueError("Correct answer must appear in options")
    if challenge.mode in (GameMode.GUESS_COUNTRY, GameMode.ASSOCIATIONS) and not challenge.hints:
        raise ValueError("Hint-based format needs hints")
