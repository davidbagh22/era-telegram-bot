import pytest

from app.services.game_formats import (
    Challenge, GameMode, check_answer, score_answer, validate_challenge,
)


@pytest.mark.parametrize("mode", list(GameMode))
def test_all_eleven_modes_have_answer_rules(mode):
    kwargs = {}
    if mode in {GameMode.SOLO_QUIZ, GameMode.TEAM_QUIZ,
                GameMode.TRUE_OR_MYTH, GameMode.CULTURE, GameMode.TEAM_DUEL}:
        kwargs["options"] = ("Ереван", "Гюмри")
    if mode in {GameMode.GUESS_COUNTRY, GameMode.ASSOCIATIONS}:
        kwargs["hints"] = ("Подсказка",)
    challenge = Challenge(mode, "Назови ответ", "Ереван", **kwargs)
    validate_challenge(challenge)
    assert check_answer(challenge, " ЕРЕВАН ")
    assert score_answer(challenge, "Ереван") > 0
    assert score_answer(challenge, "неверно") == 0


def test_hint_penalty():
    challenge = Challenge(GameMode.GUESS_COUNTRY, "Страна?", "Армения", hints=("Кавказ",))
    assert score_answer(challenge, "Армения") == 4
    assert score_answer(challenge, "Армения", hints_used=3) == 1


def test_chronology_order_is_strict():
    challenge = Challenge(GameMode.CHRONOLOGY, "Порядок?", "1,2,3")
    assert check_answer(challenge, "1, 2, 3")
    assert not check_answer(challenge, "3,2,1")


def test_memory_sequence_is_strict():
    challenge = Challenge(GameMode.MEMORY, "Запомни", "4 7 2")
    assert check_answer(challenge, "472")
    assert not check_answer(challenge, "427")


def test_word_chain_checks_starting_letter():
    challenge = Challenge(GameMode.WORD_CHAIN, "Продолжи", "арбуз")
    assert check_answer(challenge, "арбуз", previous_word="Москва")
    assert not check_answer(challenge, "арбуз", previous_word="Ереван")


def test_choice_mode_rejects_missing_correct_option():
    with pytest.raises(ValueError):
        validate_challenge(Challenge(GameMode.TRUE_OR_MYTH, "Правда?", "Да", options=("Нет", "Не знаю")))
