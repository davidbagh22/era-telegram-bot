"""Eleven explicit game formats, each with its own scoring and answer rules.

This module is deliberately independent of Telegram so its behavior can be tested.
The room handlers use these rules while managing persisted Telegram sessions.
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
        previous_letters = [character for character in normalize(previous_word) if character.isalpha()]
        while previous_letters and previous_letters[-1] in "ьъы":
            previous_letters.pop()
        return bool(previous_letters) and value.startswith(previous_letters[-1]) and value == expected
    if challenge.mode == GameMode.CHRONOLOGY:
        separator = "→" if "→" in value or "→" in expected else ","
        return tuple(normalize(part) for part in value.split(separator)) == tuple(
            normalize(part) for part in expected.split(separator)
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
                          GameMode.TRUE_OR_MYTH, GameMode.GUESS_COUNTRY,
                          GameMode.CHRONOLOGY, GameMode.WORD_CHAIN,
                          GameMode.ASSOCIATIONS, GameMode.LOGIC,
                          GameMode.CULTURE, GameMode.MEMORY, GameMode.TEAM_DUEL):
        if len(challenge.options) < 2:
            raise ValueError("Choice-based format needs at least two options")
        if len({normalize(item) for item in challenge.options}) != len(challenge.options):
            raise ValueError("Options must be unique")
        if normalize(challenge.answer) not in {normalize(item) for item in challenge.options}:
            raise ValueError("Correct answer must appear in options")
    if challenge.mode in (GameMode.GUESS_COUNTRY, GameMode.ASSOCIATIONS) and not challenge.hints:
        raise ValueError("Hint-based format needs hints")
