from __future__ import annotations

from typing import Any

LIKERT_ACCURACY = [
    {"value": 1, "label": "Совсем не похоже"},
    {"value": 2, "label": "Скорее не похоже"},
    {"value": 3, "label": "И да, и нет"},
    {"value": 4, "label": "Скорее похоже"},
    {"value": 5, "label": "Очень похоже"},
]

LIKERT_AGREEMENT = [
    {"value": 1, "label": "Совсем не согласен"},
    {"value": 2, "label": "Скорее не согласен"},
    {"value": 3, "label": "По-разному"},
    {"value": 4, "label": "Скорее согласен"},
    {"value": 5, "label": "Полностью согласен"},
]

LIKERT_INTEREST = [
    {"value": 1, "label": "Совсем не интересно"},
    {"value": 2, "label": "Скорее не интересно"},
    {"value": 3, "label": "Нейтрально"},
    {"value": 4, "label": "Скорее интересно"},
    {"value": 5, "label": "Очень интересно"},
]

WHO5_OPTIONS = [
    {"value": 5, "label": "Всё время"},
    {"value": 4, "label": "Большую часть времени"},
    {"value": 3, "label": "Более половины времени"},
    {"value": 2, "label": "Менее половины времени"},
    {"value": 1, "label": "Некоторое время"},
    {"value": 0, "label": "Никогда"},
]

GSE_OPTIONS = [
    {"value": 1, "label": "Абсолютно неверно"},
    {"value": 2, "label": "Едва ли это верно"},
    {"value": 3, "label": "Скорее всего — верно"},
    {"value": 4, "label": "Совершенно верно"},
]


def q(code: str, text: str, scale: str, *, reverse: bool = False) -> dict[str, Any]:
    return {"code": code, "text": text, "scale": scale, "reverse": reverse}


WHO5 = {
    "code": "WHO5_RU",
    "title": "Как мне сейчас?",
    "description": "Пять вопросов о субъективном благополучии за последние две недели.",
    "source": "World Health Organization",
    "methodology": "WHO-5 Well-Being Index, official Russian translation published by WHO in 2024",
    "license": "CC BY-NC-SA 3.0",
    "license_status": "approved",
    "version": "WHO-UCN-MSD-MHE-2024.01-RU",
    "language": "ru",
    "translation_source": "WHO official Russian PDF, published 2024-10-02; Russian wording predates WHO copyright transfer and is distributed by WHO.",
    "estimated_minutes": 2,
    "min_age": None,
    "retake": 14,
    "construct": "state",
    "response_scale": WHO5_OPTIONS,
    "scales": [{"code": "wellbeing", "title": "Самочувствие"}],
    "scoring": {"wellbeing": {"method": "sum_times", "factor": 4, "min": 0, "max": 100}},
    "constraints": {
        "diagnostic": False,
        "notice": "Результат отражает субъективное самочувствие за последние две недели и не является диагнозом.",
    },
    "questions": [
        q("w1", "Я чувствую себя бодрой(-ым) и в хорошем настроении.", "wellbeing"),
        q("w2", "Я чувствую себя спокойной(-ым) и раскованной(-ым).", "wellbeing"),
        q("w3", "Я чувствую себя активной(-ым) и энергичной(-ым).", "wellbeing"),
        q("w4", "Я просыпаюсь и чувствую себя свежей(-им) и отдохнувшей(-им).", "wellbeing"),
        q("w5", "Каждый день со мной происходят вещи, представляющие для меня интерес.", "wellbeing"),
    ],
}

GSE = {
    "code": "GSE_RU",
    "title": "Насколько я верю, что справлюсь?",
    "description": "Общая самоэффективность: насколько ты веришь, что способен справляться со сложными и неожиданными задачами.",
    "source": "Ralf Schwarzer, Matthias Jerusalem, Vladimir Romek",
    "methodology": "General Self-Efficacy Scale (GSE), Russian adaptation, 1996",
    "license": "Free to use and reproduce with attribution; official author documentation",
    "license_status": "approved",
    "version": "GSE-RU-ROMEK-1996",
    "language": "ru",
    "translation_source": "Official Russian adaptation by Romek, Schwarzer & Jerusalem (1996) published on the authors' FU Berlin site.",
    "estimated_minutes": 4,
    "min_age": 12,
    "retake": 60,
    "construct": "state",
    "response_scale": GSE_OPTIONS,
    "scales": [{"code": "self_efficacy", "title": "Самоэффективность"}],
    "scoring": {"self_efficacy": {"method": "sum", "min": 10, "max": 40}},
    "constraints": {
        "diagnostic": False,
        "notice": "Шкала показывает общее ощущение собственной способности справляться. Это не оценка реальных способностей и не прогноз успеха.",
    },
    "questions": [
        q("g1", "Если я как следует постараюсь, то я всегда найду решение даже сложным проблемам.", "self_efficacy"),
        q("g2", "Если мне что-либо мешает, то я всё же нахожу пути достижения своей цели.", "self_efficacy"),
        q("g3", "Мне довольно просто удаётся достичь своих целей.", "self_efficacy"),
        q("g4", "В неожиданных ситуациях я всегда знаю, как я должен себя вести.", "self_efficacy"),
        q("g5", "При непредвиденно возникающих трудностях я верю, что смогу с ними справиться.", "self_efficacy"),
        q("g6", "Если я приложу достаточно усилий, то смогу справиться с большинством проблем.", "self_efficacy"),
        q("g7", "Я готов к любым трудностям, поскольку полагаюсь на собственные способности.", "self_efficacy"),
        q("g8", "Если передо мной встаёт какая-либо проблема, то я обычно нахожу несколько вариантов её решения.", "self_efficacy"),
        q("g9", "Я могу что-либо придумать даже в безвыходных на первый взгляд ситуациях.", "self_efficacy"),
        q("g10", "Я обычно способен держать ситуацию под контролем.", "self_efficacy"),
    ],
}

BIG5_GROUPS = {
    "extraversion": {
        "title": "Проявленность среди людей",
        "positive": [
            "Вы — душа любой вечеринки.",
            "Вы чувствуете себя комфортно в кругу людей.",
            "Вы часто начинаете разговор сами.",
            "Говорите с большим количеством различных людей на вечеринках.",
            "Не возражаете быть центром внимания.",
        ],
        "negative": [
            "Не говорите много.",
            "Держитесь на заднем плане.",
            "Вы немногословны.",
            "Не любите привлекать к себе внимание.",
            "Вы мало говорите в кругу незнакомых Вам людей.",
        ],
    },
    "agreeableness": {
        "title": "Ориентация на людей",
        "positive": [
            "Люди Вам интересны.",
            "Сочувствуете чувствам других.",
            "У вас мягкое сердце.",
            "Вы уделяете время другим.",
            "Чувствуете настроения и эмоции окружающих.",
            "С вами люди чувствуют себя непринуждённо.",
        ],
        "negative": [
            "На самом деле люди вам не интересны.",
            "Вы можете оскорбить.",
            "Вам не интересны проблемы окружающих.",
            "Вы редко беспокоитесь за других.",
        ],
    },
    "conscientiousness": {
        "title": "Организованность и доведение",
        "positive": [
            "Жизнь редко застаёт Вас врасплох.",
            "Обращаете внимание на детали.",
            "Работаете эффективно.",
            "Любите порядок.",
            "Следуете распорядку или плану.",
            "Вы аккуратны в работе.",
        ],
        "negative": [
            "Часто разбрасываете вещи.",
            "Создаёте беспорядок.",
            "Часто забываете положить вещи на место.",
            "Уклоняетесь от обязанностей.",
        ],
    },
    "emotional_stability": {
        "title": "Эмоциональная устойчивость",
        "positive": [
            "Обычно спокойны.",
            "Редко грустите.",
        ],
        "negative": [
            "Легко подвергаетесь стрессу.",
            "Часто беспокоитесь.",
            "Вас легко вывести из равновесия.",
            "Легко расстраиваетесь.",
            "Часто меняете настроение.",
            "Подвержены частым колебаниям настроения.",
            "Легко раздражаетесь.",
            "Часто бываете грустны.",
        ],
    },
    "intellect": {
        "title": "Интеллект и воображение",
        "positive": [
            "У вас богатый словарный запас.",
            "У вас богатое воображение.",
            "У вас часто возникают превосходные идеи.",
            "Легко вникаете в суть вещей.",
            "Используете сложные слова.",
            "Останавливаетесь, чтобы обдумать происходящее.",
            "Полны идей.",
        ],
        "negative": [
            "Вам сложно понимать абстрактные идеи.",
            "Вы не интересуетесь абстрактными идеями.",
            "У вас не очень хорошее воображение.",
        ],
    },
}

# Standard 50-item IPIP presentation order. Translation wording is from the public-domain
# Russian 50-item factor-marker page maintained by the IPIP project.
BIG5_ORDER = [
    ("extraversion", 0, False), ("agreeableness", 3, True), ("conscientiousness", 0, False),
    ("emotional_stability", 0, True), ("intellect", 0, False), ("extraversion", 0, True),
    ("agreeableness", 0, False), ("conscientiousness", 0, True), ("emotional_stability", 0, False),
    ("intellect", 0, True), ("extraversion", 1, False), ("agreeableness", 1, True),
    ("conscientiousness", 1, False), ("emotional_stability", 1, True), ("intellect", 1, False),
    ("extraversion", 1, True), ("agreeableness", 1, False), ("conscientiousness", 1, True),
    ("emotional_stability", 1, False), ("intellect", 1, True), ("extraversion", 2, False),
    ("agreeableness", 2, True), ("conscientiousness", 2, False), ("emotional_stability", 2, True),
    ("intellect", 2, False), ("extraversion", 2, True), ("agreeableness", 2, False),
    ("conscientiousness", 2, True), ("emotional_stability", 3, True), ("intellect", 2, True),
    ("extraversion", 3, False), ("agreeableness", 0, True), ("conscientiousness", 3, False),
    ("emotional_stability", 4, True), ("intellect", 3, False), ("extraversion", 3, True),
    ("agreeableness", 3, False), ("conscientiousness", 3, True), ("emotional_stability", 5, True),
    ("intellect", 4, False), ("extraversion", 4, False), ("agreeableness", 4, False),
    ("conscientiousness", 4, False), ("emotional_stability", 6, True), ("intellect", 5, False),
    ("extraversion", 4, True), ("agreeableness", 5, False), ("conscientiousness", 5, False),
    ("emotional_stability", 7, True), ("intellect", 6, False),
]


def _big5_item(scale: str, index: int, reverse: bool) -> str:
    bucket = "negative" if reverse else "positive"
    return BIG5_GROUPS[scale][bucket][index]


BIG5_QUESTIONS = [
    q(f"b{position}", _big5_item(scale, index, reverse), scale, reverse=reverse)
    for position, (scale, index, reverse) in enumerate(BIG5_ORDER, start=1)
]

IPIP_BIG5 = {
    "code": "IPIP_BIG5_RU",
    "title": "Как я устроен?",
    "description": "Пять широких особенностей личности. Здесь нет хороших и плохих типов — важен твой собственный профиль.",
    "source": "International Personality Item Pool (IPIP), Goldberg Big-Five factor markers",
    "methodology": "50-item IPIP representation of Goldberg (1992) Big-Five factor markers",
    "license": "Public domain",
    "license_status": "approved",
    "version": "IPIP-BFM50-RU-HYPPONEN-2026-CATALOG",
    "language": "ru",
    "translation_source": "Russian translation of the 50-item lexical Big-Five factor markers provided by Olga Hypponen and published by IPIP. IPIP notes that translations are community-provided and are not verified by the IPIP project.",
    "estimated_minutes": 8,
    "min_age": 14,
    "retake": 180,
    "construct": "trait",
    "response_scale": LIKERT_ACCURACY,
    "scales": [{"code": code, "title": data["title"]} for code, data in BIG5_GROUPS.items()],
    "scoring": {code: {"method": "mean_reverse", "min": 1, "max": 5} for code in BIG5_GROUPS},
    "constraints": {
        "diagnostic": False,
        "notice": "Это профиль широких черт, а не тип личности и не рейтинг. Русский перевод опубликован IPIP, но отдельно не верифицирован самим проектом IPIP.",
    },
    "questions": BIG5_QUESTIONS,
}


def _subset(code: str, title: str, description: str, scale: str, retake: int = 120) -> dict[str, Any]:
    questions = [item for item in BIG5_QUESTIONS if item["scale"] == scale]
    return {
        "code": code,
        "title": title,
        "description": description,
        "source": "International Personality Item Pool (IPIP), Russian 50-item Big-Five factor-marker translation",
        "methodology": f"10-item focused view of the {scale} factor from the public-domain IPIP-BFM50",
        "license": "Public domain",
        "license_status": "approved",
        "version": f"IPIP-BFM50-RU-{scale.upper()}-V1",
        "language": "ru",
        "translation_source": "Same public-domain Russian item translation used in IPIP_BIG5_RU.",
        "estimated_minutes": 3,
        "min_age": 14,
        "retake": retake,
        "construct": "trait",
        "response_scale": LIKERT_ACCURACY,
        "scales": [{"code": scale, "title": BIG5_GROUPS[scale]["title"]}],
        "scoring": {scale: {"method": "mean_reverse", "min": 1, "max": 5}},
        "constraints": {
            "diagnostic": False,
            "notice": "Короткий фокус на одной части профиля. Не используем результат как оценку человека или пригодности к роли.",
        },
        "questions": questions,
    }


IPIP_FOLLOW_THROUGH = _subset(
    "IPIP_FOLLOW_THROUGH_RU",
    "Как я начинаю и довожу",
    "Организованность, внимание к деталям и привычка доводить дела.",
    "conscientiousness",
)
IPIP_SOCIAL = _subset(
    "IPIP_SOCIAL_RU",
    "Как я проявляюсь среди людей",
    "Насколько естественно тебе инициировать общение и быть заметным среди людей.",
    "extraversion",
)
IPIP_NEWNESS = _subset(
    "IPIP_NEWNESS_RU",
    "Как я реагирую на новое",
    "Идеи, воображение, размышление и интерес к сложным или абстрактным темам.",
    "intellect",
)
IPIP_INTERACTION = _subset(
    "IPIP_INTERACTION_RU",
    "Как я взаимодействую",
    "Внимание к людям, эмпатия и ориентация на сотрудничество.",
    "agreeableness",
)

RIASEC_SCALES = {
    "R": "Практическое",
    "I": "Исследовательское",
    "A": "Творческое",
    "S": "Социальное",
    "E": "Предпринимательское",
    "C": "Организационное",
}

ERA_RIASEC = {
    "code": "ERA_RIASEC_RU",
    "title": "Что мне действительно интересно?",
    "description": "Карта интересов по шести направлениям RIASEC — не про способности, а про то, какие виды деятельности тебя притягивают.",
    "source": "Holland RIASEC model; informed by O*NET Interest Profiler and current RIASEC research",
    "methodology": "ERA Russian RIASEC self-reflection inventory v1; original items mapped to the six Holland interest domains",
    "license": "ERA original wording; RIASEC construct attribution in methodology",
    "license_status": "approved",
    "version": "ERA-RIASEC-RU-V1-2026",
    "language": "ru",
    "translation_source": "Original Russian wording by ERA; not presented as an official O*NET translation or a Russian-normed psychometric instrument.",
    "estimated_minutes": 5,
    "min_age": 14,
    "retake": 120,
    "construct": "interest",
    "response_scale": LIKERT_INTEREST,
    "scales": [{"code": code, "title": title} for code, title in RIASEC_SCALES.items()],
    "scoring": {code: {"method": "mean", "min": 1, "max": 5} for code in RIASEC_SCALES},
    "constraints": {
        "diagnostic": False,
        "notice": "Это карта интересов, не тест способностей и не рекомендация профессии. Сравниваются твои собственные направления между собой.",
        "validation": "Russian ERA item set has not yet been normed on a representative sample; use for self-reflection, not selection.",
    },
    "questions": [
        q("r1", "Мне интересно собирать, настраивать или ремонтировать реальные вещи и устройства.", "R"),
        q("r2", "Мне нравится работа, где результат можно увидеть или потрогать: построить, установить, настроить, сделать руками.", "R"),
        q("r3", "Мне было бы интересно разбираться с техникой, инструментами или практическими механизмами.", "R"),
        q("i1", "Мне нравится разбираться, почему что-то работает именно так, а не иначе.", "I"),
        q("i2", "Мне интересно анализировать данные, сравнивать версии и искать закономерности.", "I"),
        q("i3", "Мне нравится изучать сложный вопрос глубже, даже если ответ не очевиден сразу.", "I"),
        q("a1", "Мне нравится придумывать необычные идеи, тексты, визуальные решения или форматы.", "A"),
        q("a2", "Мне интересно создавать что-то, где можно проявить собственный стиль и воображение.", "A"),
        q("a3", "Мне нравится импровизировать и искать нестандартный способ выразить мысль.", "A"),
        q("s1", "Мне нравится помогать человеку разобраться в вопросе или освоить что-то новое.", "S"),
        q("s2", "Мне интересно слушать людей и помогать им находить следующий шаг.", "S"),
        q("s3", "Мне нравится деятельность, где важно поддерживать, обучать или объединять людей.", "S"),
        q("e1", "Мне интересно убеждать людей в идее и собирать поддержку вокруг неё.", "E"),
        q("e2", "Мне нравится брать инициативу и вести группу к результату.", "E"),
        q("e3", "Мне интересно договариваться, презентовать идеи и запускать новые инициативы.", "E"),
        q("c1", "Мне нравится приводить информацию, документы или процессы в понятный порядок.", "C"),
        q("c2", "Мне комфортно работать по понятной системе, где важны точность и последовательность.", "C"),
        q("c3", "Мне нравится вести списки, таблицы, учёт или проверять, что детали не потерялись.", "C"),
    ],
}

ERA_NEEDS = {
    "code": "ERA_NEEDS_RU",
    "title": "Чего мне сейчас не хватает?",
    "description": "Короткий снимок трёх базовых психологических потребностей: самостоятельность, ощущение компетентности и связь с людьми.",
    "source": "Self-Determination Theory / Basic Psychological Needs Theory",
    "methodology": "ERA Basic Needs Snapshot v1; original Russian self-reflection items based on autonomy, competence and relatedness constructs",
    "license": "ERA original wording; theoretical framework attributed to Self-Determination Theory",
    "license_status": "approved",
    "version": "ERA-BASIC-NEEDS-RU-V1-2026",
    "language": "ru",
    "translation_source": "Original Russian wording. Not presented as BPNSFS/BPNSS and not scored against clinical or population norms.",
    "estimated_minutes": 3,
    "min_age": 14,
    "retake": 45,
    "construct": "state",
    "response_scale": LIKERT_AGREEMENT,
    "scales": [
        {"code": "autonomy", "title": "Самостоятельность"},
        {"code": "competence", "title": "Ощущение компетентности"},
        {"code": "relatedness", "title": "Связь с людьми"},
    ],
    "scoring": {
        "autonomy": {"method": "mean", "min": 1, "max": 5},
        "competence": {"method": "mean", "min": 1, "max": 5},
        "relatedness": {"method": "mean", "min": 1, "max": 5},
    },
    "constraints": {
        "diagnostic": False,
        "notice": "Это рефлексивный снимок на основе трёх потребностей SDT, а не официальный BPNSFS и не диагноз.",
    },
    "questions": [
        q("n1", "В важных для меня делах я чувствую, что могу выбирать способ действия сам.", "autonomy"),
        q("n2", "Мои текущие решения в целом похожи на то, чего действительно хочу я.", "autonomy"),
        q("n3", "У меня есть пространство сказать «нет» или выбрать другой путь, если это для меня важно.", "autonomy"),
        q("n4", "В большинстве текущих задач я понимаю, что способен сделать следующий шаг.", "competence"),
        q("n5", "Я замечаю, что становлюсь лучше хотя бы в некоторых важных для меня вещах.", "competence"),
        q("n6", "Сложные задачи чаще вызывают у меня интерес к решению, чем ощущение полной беспомощности.", "competence"),
        q("n7", "Есть люди, рядом с которыми я чувствую себя принятым и могу быть собой.", "relatedness"),
        q("n8", "Если мне действительно понадобится поддержка, я понимаю, к кому могу обратиться.", "relatedness"),
        q("n9", "В последнее время у меня были разговоры или встречи, после которых я чувствовал больше связи с людьми.", "relatedness"),
    ],
}

ASSESSMENTS = [
    WHO5,
    GSE,
    IPIP_BIG5,
    ERA_RIASEC,
    ERA_NEEDS,
    IPIP_FOLLOW_THROUGH,
    IPIP_SOCIAL,
    IPIP_NEWNESS,
    IPIP_INTERACTION,
]

ASSESSMENT_BY_CODE = {item["code"]: item for item in ASSESSMENTS}

STRENGTHS_DEFINITION = {
    "code": "STRENGTHS_SYNTHESIS",
    "title": "Мои сильные стороны",
    "description": "Синтез уже накопленных результатов — не отдельный тест.",
    "source": "ERA interpretation layer",
    "methodology": "Derived profile from completed assessments; no independent psychological scoring",
    "license": "ERA internal synthesis",
    "license_status": "available_after_data",
    "estimated_minutes": 0,
    "min_age": None,
    "retake": 30,
    "construct": "derived",
}
