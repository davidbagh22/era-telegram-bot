from app.handlers.era_game_room import QUESTIONS
from app.services.game_content import items_for_mode
from app.services.game_formats import GameMode, check_answer, validate_challenge


def test_quiz_bank_contains_reviewable_thematic_questions():
    prompts = [prompt for prompt, _, _ in QUESTIONS]
    assert len(QUESTIONS) >= 180
    assert len(prompts) == len(set(prompts))
    assert all("Сколько будет" not in prompt for prompt in prompts)


def test_quiz_bank_has_one_valid_answer_and_distinct_distractors():
    for prompt, choices, correct in QUESTIONS:
        assert prompt.strip()
        assert len(choices) == len(set(choices)) == 3
        assert 0 <= correct < len(choices)
        assert choices[correct].strip()


def test_all_11_modes_have_180_unique_checkable_content_items():
    for mode in GameMode:
        items = items_for_mode(mode)
        assert len(items) >= 180, mode
        assert len({item.id for item in items}) == len(items), mode
        tasks = {
            (item.challenge.prompt, item.challenge.answer, item.challenge.options,
             item.challenge.hints, item.category)
            for item in items
        }
        assert len(tasks) == len(items), mode
        for item in items:
            validate_challenge(item.challenge)
            assert item.challenge.answer in item.challenge.options, item.id
            assert check_answer(
                item.challenge, item.challenge.answer, previous_word=item.previous_word
            ), item.id


def test_country_and_association_items_have_three_ordered_hints():
    for mode in (GameMode.GUESS_COUNTRY, GameMode.ASSOCIATIONS):
        assert all(len(item.challenge.hints) == 3 for item in items_for_mode(mode))


def test_quiz_themes_cover_requested_subjects():
    categories = {item.category for item in items_for_mode(GameMode.SOLO_QUIZ)}
    assert {
        "Армения", "Россия", "Мировая культура", "История", "География",
        "Литература", "Наука", "Языки", "Молодёжные проекты", "Логика",
    } <= categories
