from app.handlers.era_game_room import QUESTIONS, _arithmetic_questions


def test_generated_question_bank_has_180_distinct_questions():
    generated = _arithmetic_questions()
    assert len(generated) == 180
    assert len({question for question, _, _ in generated}) == 180
    assert len(QUESTIONS) >= 180


def test_generated_questions_have_one_correct_answer_and_three_unique_choices():
    for index, (question, choices, correct) in enumerate(_arithmetic_questions()):
        assert question.endswith("?")
        assert len(choices) == len(set(choices)) == 3
        assert correct in range(3)
        a = 12 + index
        b = 3 + index % 17
        expected = a + b if index % 3 == 0 else a if index % 3 == 1 else a * b
        assert choices[correct] == str(expected)
