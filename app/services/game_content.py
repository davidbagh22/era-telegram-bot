"""Versioned, source-backed prompts used by the Telegram game modes.

Content is kept outside callbacks so that each mode can be reviewed and extended
without changing the room state machine. Factual snapshots carry source IDs;
no arithmetic-generated items are treated as the production content bank.
"""
import hashlib
import json
import random
import re
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path

from app.services.game_formats import Challenge, GameMode


@dataclass(frozen=True)
class GameItem:
    id: str
    challenge: Challenge
    category: str
    previous_word: str = ""


# Stable reviewed multiple-choice content shared by the quick quiz, team quiz,
# and team duel. Each tuple is (prompt, choices, correct-choice-index).
QUIZ_QUESTIONS: tuple[tuple[str, tuple[str, ...], int], ...] = (
    ("Какой город является столицей Армении?", ("Ереван", "Гюмри", "Ванадзор"), 0),
    ("Как называется самый большой океан Земли?", ("Атлантический", "Индийский", "Тихий"), 2),
    ("Какая планета ближе всего к Солнцу?", ("Венера", "Меркурий", "Марс"), 1),
    ("Какой язык является государственным в Республике Армения?", ("Армянский", "Грузинский", "Персидский"), 0),
    ("Что означает QR в названии QR-кода?", ("Quick Response", "Quality Record", "Query Route"), 0),
    ("Кто написал роман «Мастер и Маргарита»?", ("Михаил Булгаков", "Михаил Шолохов", "Иван Бунин"), 0),
    ("Кто написал роман «Война и мир»?", ("Лев Толстой", "Фёдор Достоевский", "Иван Тургенев"), 0),
    ("Как называется самая крупная планета Солнечной системы?", ("Сатурн", "Юпитер", "Нептун"), 1),
    ("Кто написал картину «Герника»?", ("Пабло Пикассо", "Сальвадор Дали", "Анри Матисс"), 0),
    ("В каком городе находится Лувр?", ("Париж", "Рим", "Мадрид"), 0),
    ("Кто написал музыку балета «Спартак»?", ("Арам Хачатурян", "Комитас", "Александр Арутюнян"), 0),
    ("Как называется традиционная валюта Армении?", ("Драм", "Лари", "Манат"), 0),
    ("Кому приписывают создание армянского алфавита?", ("Месропу Маштоцу", "Григорию Просветителю", "Мовсесу Хоренаци"), 0),
    ("Какое озеро является крупнейшим в Армении?", ("Севан", "Парз", "Арпи"), 0),
    ("Какой город является столицей Грузии?", ("Тбилиси", "Батуми", "Кутаиси"), 0),
    ("Какой город является столицей России?", ("Москва", "Казань", "Санкт-Петербург"), 0),
    ("Какой город является столицей Франции?", ("Париж", "Лион", "Марсель"), 0),
    ("Какой город является столицей Италии?", ("Рим", "Милан", "Неаполь"), 0),
    ("Какой город является столицей Японии?", ("Токио", "Осака", "Киото"), 0),
    ("Какой город является столицей Канады?", ("Оттава", "Торонто", "Ванкувер"), 0),
    ("Какой город является столицей Австралии?", ("Канберра", "Сидней", "Мельбурн"), 0),
    ("Какой город является столицей Бразилии?", ("Бразилиа", "Рио-де-Жанейро", "Сан-Паулу"), 0),
    ("Какой город является столицей Казахстана?", ("Астана", "Алматы", "Шымкент"), 0),
    ("Какой город является столицей Кыргызстана?", ("Бишкек", "Ош", "Каракол"), 0),
    ("Какой город является столицей Узбекистана?", ("Ташкент", "Самарканд", "Бухара"), 0),
    ("Какой город является столицей Греции?", ("Афины", "Салоники", "Патры"), 0),
    ("Какой город является столицей Португалии?", ("Лиссабон", "Порту", "Брага"), 0),
    ("Как называется самая длинная река Европы?", ("Волга", "Дунай", "Рейн"), 0),
    ("Какое озеро считается самым глубоким в мире?", ("Байкал", "Танганьика", "Каспийское море"), 0),
    ("Какой газ растения поглощают при фотосинтезе?", ("Углекислый газ", "Кислород", "Азот"), 0),
    ("Какова химическая формула воды?", ("H₂O", "CO₂", "NaCl"), 0),
    ("Какой химический символ у золота?", ("Au", "Ag", "Fe"), 0),
    ("Как называется единица измерения электрического тока?", ("Ампер", "Ватт", "Вольт"), 0),
    ("Как называется центр атома?", ("Ядро", "Орбита", "Молекула"), 0),
    ("Какой орган перекачивает кровь по организму?", ("Сердце", "Печень", "Лёгкие"), 0),
    ("Как называется процесс превращения воды в пар?", ("Испарение", "Конденсация", "Замерзание"), 0),
    ("Кто первым ступил на поверхность Луны в рамках миссии Apollo 11?", ("Нил Армстронг", "Юрий Гагарин", "Базз Олдрин"), 0),
    ("Как называется прибор для измерения температуры?", ("Термометр", "Барометр", "Гигрометр"), 0),
    ("Кто написал повесть «Маленький принц»?", ("Антуан де Сент-Экзюпери", "Жюль Верн", "Виктор Гюго"), 0),
    ("Кто является автором трагедии «Гамлет»?", ("Уильям Шекспир", "Чарльз Диккенс", "Джон Мильтон"), 0),
    ("Как называется главный музейный комплекс на Дворцовой площади в Санкт-Петербурге?", ("Эрмитаж", "Русский музей", "Третьяковская галерея"), 0),
    ("Кто написал повесть «Капитанская дочка»?", ("Александр Пушкин", "Николай Гоголь", "Михаил Лермонтов"), 0),
    ("Какой инструмент является главным в армянском дудуке?", ("Дудук", "Канон", "Зурна"), 0),
    ("Как называется армянский средневековый монастырский комплекс у ущелья реки Азат?", ("Гегард", "Татев", "Санаин"), 0),
    ("Какой материк занимает наибольшую площадь?", ("Азия", "Африка", "Европа"), 0),
    ("Как называется линия, делящая Землю на Северное и Южное полушария?", ("Экватор", "Нулевой меридиан", "Тропик Козерога"), 0),
    ("Какой океан омывает восточное побережье Африки?", ("Индийский", "Тихий", "Северный Ледовитый"), 0),
    ("В какой стране находится город Самарканд?", ("Узбекистан", "Казахстан", "Таджикистан"), 0),
    ("В какой стране находится город Краков?", ("Польша", "Чехия", "Словакия"), 0),
    ("Какой язык относится к индоевропейской языковой семье?", ("Русский", "Японский", "Баскский"), 0),
    ("Какой язык использует письменность хангыль?", ("Корейский", "Тайский", "Вьетнамский"), 0),
    ("Как называется наука о живых организмах?", ("Биология", "Геология", "Астрономия"), 0),
    ("Как называется наука о небесных телах и Вселенной?", ("Астрономия", "Экология", "Ботаника"), 0),
    ("Какой материк полностью покрыт льдом и не имеет постоянного коренного населения?", ("Антарктида", "Австралия", "Южная Америка"), 0),
    ("В каком городе расположен музей Прадо?", ("Мадрид", "Барселона", "Севилья"), 0),
    ("Кто написал роман «Преступление и наказание»?", ("Фёдор Достоевский", "Лев Толстой", "Иван Гончаров"), 0),
    ("Какой композитор создал балет «Лебединое озеро»?", ("Пётр Чайковский", "Модест Мусоргский", "Сергей Рахманинов"), 0),
    ("Как называется письменность, которой записывают японский язык наряду с кандзи?", ("Хирагана", "Хангыль", "Деванагари"), 0),
    ("Как называется единица наследственной информации в ДНК?", ("Ген", "Нейрон", "Атом"), 0),
    ("Какая часть растения обычно поглощает воду из почвы?", ("Корень", "Лепесток", "Плод"), 0),
    ("Какой город был столицей Византийской империи и сегодня называется Стамбул?", ("Константинополь", "Александрия", "Антиохия"), 0),
    ("Как называется самая высокая гора Армении?", ("Арагац", "Арарат", "Капутджух"), 0),
    ("Какая страна известна историческим городом Киото?", ("Япония", "Китай", "Южная Корея"), 0),
    ("Какой металл обозначается химическим символом Fe?", ("Железо", "Медь", "Серебро"), 0),
    ("Как называется специалист, изучающий прошлое по материальным находкам?", ("Археолог", "Метеоролог", "Лингвист"), 0),
)


ITEMS: dict[GameMode, tuple[GameItem, ...]] = {
    GameMode.TRUE_OR_MYTH: (
        GameItem("tom-armenia-001", Challenge(
            GameMode.TRUE_OR_MYTH,
            "Ереван основан раньше Рима.", "Правда", ("Правда", "Миф"),
            explanation="Эребуни, крепость на месте современного Еревана, основана в 782 году до н. э.; традиционная дата основания Рима — 753 год до н. э.",
        ), "Армения"),
        GameItem("tom-culture-001", Challenge(
            GameMode.TRUE_OR_MYTH,
            "Роман «Мастер и Маргарита» написал Михаил Булгаков.", "Правда", ("Правда", "Миф"),
            explanation="Автор романа — Михаил Афанасьевич Булгаков.",
        ), "Литература"),
    ),
    GameMode.GUESS_COUNTRY: (
        GameItem("country-armenia-001", Challenge(
            GameMode.GUESS_COUNTRY, "Какая это страна?", "Армения",
            ("Армения", "Грузия", "Иран", "Россия"),
            ("Это страна Южного Кавказа без выхода к морю.", "На её территории находится озеро Севан.", "Столица страны — Ереван."),
            "Ереван — столица Армении.",
        ), "География"),
        GameItem("country-russia-001", Challenge(
            GameMode.GUESS_COUNTRY, "Какая это страна?", "Россия",
            ("Россия", "Казахстан", "Монголия", "Китай"),
            ("Это крупнейшая по площади страна мира.", "Её территорию омывают моря трёх океанов.", "Столица страны — Москва."),
            "Россия — крупнейшее государство мира по площади.",
        ), "География"),
    ),
    GameMode.CHRONOLOGY: (
        GameItem("chronology-armenian-001", Challenge(
            GameMode.CHRONOLOGY, "Расположи события от самого раннего к позднему.",
            "Основание Эребуни, основание Рима, создание армянского алфавита",
            ("Основание Эребуни, основание Рима, создание армянского алфавита",
             "Основание Рима, основание Эребуни, создание армянского алфавита",
             "Создание армянского алфавита, основание Эребуни, основание Рима"),
            explanation="Эребуни основана в 782 году до н. э.; традиционная дата основания Рима — 753 год до н. э.; армянский алфавит создан около 405 года н. э.",
        ), "История"),
        GameItem("chronology-literature-001", Challenge(
            GameMode.CHRONOLOGY, "Расположи события от самого раннего к позднему.",
            "Публикация «Робинзона Крузо», публикация «Франкенштейна», публикация «Мастера и Маргариты»",
            ("Публикация «Робинзона Крузо», публикация «Франкенштейна», публикация «Мастера и Маргариты»",
             "Публикация «Франкенштейна», публикация «Робинзона Крузо», публикация «Мастера и Маргариты»",
             "Публикация «Мастера и Маргариты», публикация «Франкенштейна», публикация «Робинзона Крузо»"),
            explanation="«Робинзон Крузо» вышел в 1719 году, «Франкенштейн» — в 1818-м; роман Булгакова опубликован полностью в 1967 году.",
        ), "Литература"),
    ),
    GameMode.WORD_CHAIN: (
        GameItem("word-chain-001", Challenge(
            GameMode.WORD_CHAIN, "Продолжи цепочку: Ереван → ?", "Норильск",
            ("Норильск", "Тбилиси", "Москва", "Сочи"), explanation="«Ереван» заканчивается на «н», а «Норильск» начинается на «н»."), "География", "Ереван"),
        GameItem("word-chain-002", Challenge(
            GameMode.WORD_CHAIN, "Продолжи цепочку: книга → ?", "Архив",
            ("Архив", "Музей", "Театр", "Сцена"), explanation="«Книга» заканчивается на «а», а «Архив» начинается на «а»."), "Культура", "Книга"),
    ),
    GameMode.ASSOCIATIONS: (
        GameItem("association-matenadaran-001", Challenge(
            GameMode.ASSOCIATIONS, "Угадай место по подсказкам.", "Матенадаран",
            ("Матенадаран", "Галерея Третьякова", "Эрмитаж", "Национальная библиотека"),
            ("Это научно-исследовательский институт и музей в Ереване.",
             "Его коллекция связана с рукописным наследием.",
             "Учреждение носит имя Месропа Маштоца."),
            "Матенадаран хранит и изучает древние рукописи.",
        ), "Армения"),
        GameItem("association-louvre-001", Challenge(
            GameMode.ASSOCIATIONS, "Угадай место по подсказкам.", "Лувр",
            ("Лувр", "Прадо", "Уффици", "Эрмитаж"),
            ("Это музей в столице европейского государства.",
             "В его коллекции находится «Мона Лиза».",
             "Он расположен в Париже."),
            "«Мона Лиза» входит в коллекцию Лувра.",
        ), "Мировая культура"),
    ),
    GameMode.LOGIC: (
        GameItem("logic-books-001", Challenge(
            GameMode.LOGIC, "На полке три книги: красная стоит левее синей, зелёная — правее синей. Какая книга в центре?",
            "Синяя", ("Красная", "Синяя", "Зелёная", "Определить нельзя"),
            explanation="Красная левее синей, а зелёная правее синей: порядок однозначен — красная, синяя, зелёная."), "Логика"),
        GameItem("logic-seats-001", Challenge(
            GameMode.LOGIC, "Ани сидит левее Мари, а Мари левее Давида. Кто сидит посередине?",
            "Мари", ("Ани", "Мари", "Давид", "Недостаточно данных"),
            explanation="Из условий следует порядок Ани — Мари — Давид."), "Логика"),
    ),
    GameMode.CULTURE: (
        GameItem("culture-bulgakov-001", Challenge(
            GameMode.CULTURE, "Кто написал роман «Мастер и Маргарита»?", "Михаил Булгаков",
            ("Михаил Булгаков", "Михаил Шолохов", "Иван Бунин", "Александр Куприн"),
            explanation="Автор романа — Михаил Булгаков."), "Литература"),
        GameItem("culture-khachaturian-001", Challenge(
            GameMode.CULTURE, "Какой армянский композитор написал балет «Спартак»?", "Арам Хачатурян",
            ("Арам Хачатурян", "Комитас", "Александр Арутюнян", "Микаэл Таривердиев"),
            explanation="«Спартак» — балет Арама Хачатуряна."), "Армения"),
    ),
    GameMode.MEMORY: (
        GameItem("memory-colors-001", Challenge(
            GameMode.MEMORY, "Запомни последовательность и выбери её без перестановок: 🔴 🔵 🟡",
            "красный синий жёлтый",
            ("красный синий жёлтый", "синий красный жёлтый", "красный жёлтый синий", "жёлтый синий красный"),
            explanation="Порядок символов: красный, синий, жёлтый."), "Память"),
        GameItem("memory-shapes-001", Challenge(
            GameMode.MEMORY, "Запомни последовательность и выбери её: ▲ ● ■",
            "треугольник круг квадрат",
            ("треугольник круг квадрат", "круг треугольник квадрат", "квадрат круг треугольник", "треугольник квадрат круг"),
            explanation="Порядок символов: треугольник, круг, квадрат."), "Память"),
    ),
}


_CONTENT_DIR = Path(__file__).parent


def _load_records(filename: str) -> tuple[dict, ...]:
    payload = json.loads((_CONTENT_DIR / filename).read_text(encoding="utf-8"))
    return tuple(payload["records"])


# Factual source snapshots are offline at runtime, tied to stable Wikidata IDs,
# and kept outside Telegram callbacks. Wikidata's structured facts are CC0.
COUNTRY_FACTS = _load_records("game_countries.json")
CULTURE_FACTS = _load_records("game_culture_facts.json")
HISTORICAL_EVENTS = _load_records("game_historical_events.json")


def _choice_options(correct: str, distractors, *, index: int, count: int = 4) -> tuple[str, ...]:
    pool = []
    for option in distractors:
        if option and normalize_content(option) != normalize_content(correct) and option not in pool:
            pool.append(option)
        if len(pool) == count - 1:
            break
    if len(pool) < count - 1:
        return ()
    result = pool
    result.insert(index % count, correct)
    return tuple(result)


def normalize_content(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def _interleave_by_category(records: tuple[dict, ...]) -> tuple[dict, ...]:
    groups: dict[str, list[dict]] = {}
    for record in records:
        groups.setdefault(record.get("category", "Культура"), []).append(record)
    categories = sorted(groups)
    mixed = []
    while any(groups.values()):
        for category in categories:
            if groups[category]:
                mixed.append(groups[category].pop(0))
    return tuple(mixed)


WORKS = _interleave_by_category(CULTURE_FACTS)
_COUNTRY_BY_ID = {record["id"]: record for record in COUNTRY_FACTS}
_CULTURE_PROMPTS: list[tuple[str, tuple[str, ...], int]] = []
_seen_quiz_prompts = {normalize_content(prompt) for prompt, _, _ in QUIZ_QUESTIONS}


def _country_distractors(record: dict) -> list[str]:
    regions = set(record.get("continents", ()))
    same_region = [
        candidate["name"] for candidate in COUNTRY_FACTS
        if candidate["id"] != record["id"]
        and regions.intersection(candidate.get("continents", ()))
    ]
    fallback = [candidate["name"] for candidate in COUNTRY_FACTS if candidate["id"] != record["id"]]
    return list(dict.fromkeys(same_region + fallback))


def _capital_distractors(record: dict) -> list[str]:
    regions = set(record.get("continents", ()))
    same_region = [
        candidate["capital"] for candidate in COUNTRY_FACTS
        if candidate["id"] != record["id"]
        and regions.intersection(candidate.get("continents", ()))
    ]
    fallback = [candidate["capital"] for candidate in COUNTRY_FACTS if candidate["id"] != record["id"]]
    return list(dict.fromkeys(same_region + fallback))


for index, record in enumerate(COUNTRY_FACTS):
    prompt = f"Столица какого государства — {record['capital']}?"
    if normalize_content(prompt) in _seen_quiz_prompts:
        continue
    options = _choice_options(record["name"], _country_distractors(record), index=index, count=3)
    if options:
        _CULTURE_PROMPTS.append((prompt, options, options.index(record["name"])))
        _seen_quiz_prompts.add(normalize_content(prompt))

for index, record in enumerate(WORKS):
    category = record["category"]
    noun = "книгу" if category == "Литература" else "картину"
    verb = "написал" if category == "Литература" else "создал"
    prompt = f"Кто {verb} {noun} «{record['title']}»?"
    if normalize_content(prompt) in _seen_quiz_prompts:
        continue
    distractors = [
        candidate["creator"] for candidate in WORKS
        if candidate["category"] == category and candidate["creator_id"] != record["creator_id"]
    ]
    distractors += [candidate["creator"] for candidate in WORKS if candidate["creator_id"] != record["creator_id"]]
    options = _choice_options(record["creator"], distractors, index=index, count=3)
    if options:
        _CULTURE_PROMPTS.append((prompt, options, options.index(record["creator"])))
        _seen_quiz_prompts.add(normalize_content(prompt))

# Youth-project facts checked against the organizations' official descriptions
# on 2026-10-11: tumo.org/whatistumo/, tumo.org/education-program/ and
# youth.europa.eu/solidarity/{activity,organisations/solidarity-projects}_en.
YOUTH_QUESTIONS = (
    ("Какой образовательный центр Армении предлагает бесплатную программу для подростков?",
     ("TUMO", "Ереванский государственный университет", "Матенадаран"), 0),
    ("Из каких частей состоит учебная программа TUMO?",
     ("Самостоятельные занятия, воркшопы и проектные лаборатории",
      "Только лекции и экзамены", "Только спортивные тренировки"), 0),
    ("Сколько учебных направлений объединяет программа TUMO?",
     ("10", "12", "14"), 2),
    ("Какова цель Европейского корпуса солидарности?",
     ("Поддерживать участие молодёжи в волонтёрских и солидарных проектах",
      "Проводить вступительные экзамены в вузы", "Выдавать туристические визы"), 0),
    ("Что могут сделать участники молодёжного проекта солидарности?",
     ("Запустить проект для своего сообщества в стране проживания",
      "Только участвовать в международной олимпиаде", "Только пройти языковой тест"), 0),
    ("Сколько участников может быть в волонтёрской команде Европейского корпуса солидарности?",
     ("От 2 до 8", "От 10 до 40", "От 50 до 100"), 1),
)

LOGIC_QUESTIONS = (
    ("Ани стоит левее Мари, а Мари левее Давида. Кто стоит посередине?",
     ("Ани", "Мари", "Давид"), 1),
    ("В очереди Левон раньше Ани, а Ани раньше Мари. Кто второй?",
     ("Левон", "Ани", "Мари"), 1),
    ("В маршруте Ереван идёт после Гюмри, но до Ванадзора. Какая остановка в середине?",
     ("Ереван", "Гюмри", "Ванадзор"), 0),
)

_BASE_QUIZ_QUESTIONS = QUIZ_QUESTIONS
QUIZ_QUESTIONS = (tuple(_BASE_QUIZ_QUESTIONS) + tuple(_CULTURE_PROMPTS)
                  + YOUTH_QUESTIONS + LOGIC_QUESTIONS)


def _country_items() -> tuple[GameItem, ...]:
    items = []
    for index, record in enumerate(COUNTRY_FACTS):
        country = record["name"]
        capital = record["capital"]
        continents = ", ".join(record.get("continents", ())) or "не указано"
        first_letter = next((letter.upper() for letter in capital if letter.isalpha()), "?")
        letter_count = sum(letter.isalpha() for letter in capital)
        options = _choice_options(country, _country_distractors(record), index=index)
        if not options:
            continue
        hints = (
            f"Это государство расположено в регионе: {continents}.",
            f"Его столица начинается на «{first_letter}» и содержит {letter_count} букв.",
            f"Столица этого государства — {capital}.",
        )
        items.append(GameItem(
            f"country-{record['id'].casefold()}",
            Challenge(GameMode.GUESS_COUNTRY, "Определи страну по трём подсказкам.", country,
                      options, hints, f"{capital} — столица государства {country}."),
            "География",
        ))
    return tuple(items)


def _truth_items() -> tuple[GameItem, ...]:
    facts = []
    for index, record in enumerate(WORKS[:120]):
        category = record["category"]
        distractor = next((candidate["creator"] for candidate in WORKS
                           if candidate["category"] == category
                           and candidate["creator_id"] != record["creator_id"]), None)
        if not distractor:
            continue
        is_true = index % 2 == 0
        claimed_creator = record["creator"] if is_true else distractor
        statement = f"Произведение «{record['title']}» {('написал' if category == 'Литература' else 'создал')} {claimed_creator}."
        answer = "Правда" if is_true else "Миф"
        explanation = (f"Да: «{record['title']}» — работа {record['creator']}." if is_true
                       else f"Миф. «{record['title']}» — работа {record['creator']}.")
        facts.append(GameItem(
            f"truth-work-{record['id'].casefold()}",
            Challenge(GameMode.TRUE_OR_MYTH, f"{statement} Правда или миф?", answer,
                      ("Правда", "Миф"), explanation=explanation),
            category,
        ))
    for index, record in enumerate(COUNTRY_FACTS[:60]):
        distractor = next((candidate["capital"] for candidate in COUNTRY_FACTS
                           if candidate["id"] != record["id"]
                           and set(record.get("continents", ())).intersection(candidate.get("continents", ()))
                           and candidate["capital"] != record["capital"]), None)
        if not distractor:
            continue
        is_true = index % 2 == 0
        claimed_capital = record["capital"] if is_true else distractor
        answer = "Правда" if is_true else "Миф"
        statement = f"Столица государства {record['name']} — {claimed_capital}."
        explanation = (f"Верно: столица {record['name']} — {record['capital']}." if is_true
                       else f"Миф. Столица {record['name']} — {record['capital']}.")
        facts.append(GameItem(
            f"truth-country-{record['id'].casefold()}",
            Challenge(GameMode.TRUE_OR_MYTH, f"{statement} Правда или миф?", answer,
                      ("Правда", "Миф"), explanation=explanation),
            "География",
        ))
    return tuple(facts)


def _culture_items(*, associations: bool = False) -> tuple[GameItem, ...]:
    items = []
    unique_works = []
    seen_titles = set()
    for record in WORKS:
        title_key = normalize_content(record["title"])
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_works.append(record)
    for index, record in enumerate(unique_works[:180]):
        category = record["category"]
        same_category = [candidate for candidate in unique_works
                         if candidate["category"] == category and candidate["id"] != record["id"]]
        if associations:
            correct = record["title"]
            distractors = [candidate["title"] for candidate in same_category]
            options = _choice_options(correct, distractors, index=index)
            title_letters = sum(letter.isalpha() for letter in correct)
            first_letter = next((letter.upper() for letter in correct if letter.isalpha()), "?")
            hints = (f"Это произведение относится к категории «{category.lower()}».",
                     f"Создатель произведения — {record['creator']}.",
                     f"Название начинается на «{first_letter}» и содержит {title_letters} букв.")
            challenge = Challenge(GameMode.ASSOCIATIONS, "Угадай произведение по подсказкам.",
                                  correct, options, hints,
                                  f"«{correct}» — произведение {record['creator']}.")
            item_id = f"association-{record['id'].casefold()}"
            label = category
        else:
            correct = record["creator"]
            distractors = [candidate["creator"] for candidate in same_category]
            options = _choice_options(correct, distractors, index=index)
            verb = "написал" if category == "Литература" else "создал"
            noun = "книгу" if category == "Литература" else "картину"
            challenge = Challenge(GameMode.CULTURE,
                                  f"Кто {verb} {noun} «{record['title']}»?", correct,
                                  options, explanation=f"«{record['title']}» — произведение {correct}.")
            item_id = f"culture-{record['id'].casefold()}"
            label = category
        if options:
            items.append(GameItem(item_id, challenge, label))
    return tuple(items)


def _year(record: dict) -> int | None:
    match = re.match(r"^([+-]?\d+)", record.get("date", ""))
    return int(match.group(1)) if match else None


def _chronology_items() -> tuple[GameItem, ...]:
    by_title_year = {}
    for record in HISTORICAL_EVENTS:
        year = _year(record)
        title = record.get("title", "").strip()
        if year is not None and title:
            by_title_year.setdefault((normalize_content(title), year),
                                     {"id": record["id"], "title": title, "year": year})
    events = list(by_title_year.values())
    if len(events) < 10:
        return ()
    rng = random.Random("era-chronology-content-v1")
    result = []
    seen = set()
    for _ in range(50_000):
        chosen = rng.sample(events, 3)
        if len({item["year"] for item in chosen}) != 3:
            continue
        ordered = sorted(chosen, key=lambda item: (item["year"], item["title"].casefold()))
        ids = tuple(item["id"] for item in ordered)
        if ids in seen:
            continue
        seen.add(ids)
        answer = " → ".join(item["title"] for item in ordered)
        wrong_reverse = " → ".join(item["title"] for item in reversed(ordered))
        wrong_swap = " → ".join((ordered[1]["title"], ordered[0]["title"], ordered[2]["title"]))
        options = (answer, wrong_reverse, wrong_swap)
        displayed = rng.sample(ordered, 3)
        years = " → ".join(f"{item['title']} ({abs(item['year'])}{' до н. э.' if item['year'] < 0 else ''})"
                            for item in ordered)
        prompt = "Расположи события от раннего к позднему:\n" + "\n".join(
            f"• {item['title']}" for item in displayed
        )
        result.append(GameItem(
            "chronology-" + "-".join(ids),
            Challenge(GameMode.CHRONOLOGY, prompt, answer, options,
                      explanation=f"По годам: {years}."),
            "История",
        ))
        if len(result) == 180:
            break
    return tuple(result)


def _content_words() -> tuple[str, ...]:
    words = [record[field] for record in COUNTRY_FACTS for field in ("name", "capital")]
    return tuple(sorted({word.strip() for word in words if word.strip()}, key=str.casefold))


def _last_letter(word: str) -> str:
    letters = [letter for letter in normalize_content(word) if letter.isalpha()]
    while letters and letters[-1] in "ьъы":
        letters.pop()
    return letters[-1] if letters else ""


def _word_chain_items() -> tuple[GameItem, ...]:
    words = _content_words()
    result = []
    for index, previous in enumerate(words):
        initial = _last_letter(previous)
        if not initial:
            continue
        successors = [word for word in words if word != previous and normalize_content(word).startswith(initial)]
        if not successors:
            continue
        answer = successors[index % len(successors)]
        distractors = [word for word in words if word != previous and not normalize_content(word).startswith(initial)]
        options = _choice_options(answer, distractors[index % max(1, len(distractors)):]
                                  + distractors[:index % max(1, len(distractors))], index=index)
        if not options:
            continue
        item_id = hashlib.sha1(f"{previous}|{answer}".encode()).hexdigest()[:16]
        result.append(GameItem(
            f"word-chain-{item_id}",
            Challenge(GameMode.WORD_CHAIN, f"Продолжи географическую цепочку: {previous} → ?",
                      answer, options,
                      explanation=f"«{previous}» заканчивается на «{initial}», а «{answer}» начинается на эту букву."),
            "География · словесная игра", previous,
        ))
        if len(result) == 180:
            break
    return tuple(result)


def _logic_items() -> tuple[GameItem, ...]:
    words = _content_words()
    result = []
    patterns = (
        ("На полке стоят три книги: {a}, {b}, {c}. {a} левее {b}, а {b} левее {c}. Какая книга в центре?", 1,
         "Из условий следует порядок {a} → {b} → {c}."),
        ("В очереди стоят {a}, {b}, {c}. {b} стоит раньше {a}, а {a} раньше {c}. Кто посередине?", 0,
         "Порядок очереди: {b} → {a} → {c}."),
        ("На маршруте три остановки: {a}, {b}, {c}. {c} идёт раньше {a}, а {a} раньше {b}. Какая остановка в середине?", 0,
         "Порядок маршрута: {c} → {a} → {b}."),
    )
    for index in range(min(180, len(words) - 2)):
        a, b, c = words[index:index + 3]
        template, answer_index, explanation = patterns[index % len(patterns)]
        answer = (a, b, c)[answer_index]
        options = _choice_options(answer, (a, b, c, "Недостаточно данных"), index=index)
        result.append(GameItem(
            f"logic-order-{index + 1:03d}",
            Challenge(GameMode.LOGIC, template.format(a=a, b=b, c=c), answer,
                      options, explanation=explanation.format(a=a, b=b, c=c)),
            "Логика · порядок",
        ))
    return tuple(result)


def _memory_items() -> tuple[GameItem, ...]:
    words = _content_words()
    result = []
    for index in range(min(180, len(words) - 2)):
        sequence = tuple(words[index:index + 3])
        answer = " → ".join(sequence)
        alternatives = [" → ".join(item) for item in permutations(sequence) if item != sequence]
        options = _choice_options(answer, alternatives, index=index)
        if not options:
            continue
        result.append(GameItem(
            f"memory-place-{index + 1:03d}",
            Challenge(GameMode.MEMORY, f"Запомни порядок трёх названий: {answer}", answer,
                      options, explanation=f"Правильная последовательность: {answer}."),
            "География · память",
        ))
    return tuple(result)


def _quiz_items(mode: GameMode) -> tuple[GameItem, ...]:
    items = []
    for index, (prompt, options, answer_index) in enumerate(QUIZ_QUESTIONS):
        normalized_prompt = normalize_content(prompt)
        if "tumo" in normalized_prompt or "корпус солидарности" in normalized_prompt or "молодёжного проекта" in normalized_prompt:
            category = "Молодёжные проекты"
        elif "армян" in normalized_prompt or "ереван" in normalized_prompt or "армени" in normalized_prompt:
            category = "Армения"
        elif "росси" in normalized_prompt or "русск" in normalized_prompt or "москв" in normalized_prompt:
            category = "Россия"
        elif "язык" in normalized_prompt or "письменность" in normalized_prompt or "хангыль" in normalized_prompt:
            category = "Языки"
        elif any(term in normalized_prompt for term in ("левее", "очереди", "маршруте", "посередине", "второй?")):
            category = "Логика"
        elif any(term in normalized_prompt for term in ("наука", "химическ", "атом", "планет", "биолог", "астроном", "ген " , "фотосинтез")):
            category = "Наука"
        elif any(term in normalized_prompt for term in ("истори", "основан", "византий", "столет", "древн")):
            category = "История"
        elif any(term in normalized_prompt for term in ("столиц", "океан", "материк", "озер", "рек", "гор", "стране", "страна")):
            category = "География"
        elif any(term in normalized_prompt for term in ("написал", "автор", "роман", "книгу", "писател")):
            category = "Литература"
        elif any(term in normalized_prompt for term in ("картину", "музык", "музей", "балет", "композитор")):
            category = "Мировая культура"
        else:
            category = "Общие знания"
        items.append(GameItem(
            f"{mode.value}-{index + 1:03d}",
            Challenge(mode, prompt, options[answer_index], options),
            category,
        ))
    return tuple(items)


ITEMS[GameMode.SOLO_QUIZ] = _quiz_items(GameMode.SOLO_QUIZ)
ITEMS[GameMode.TEAM_QUIZ] = _quiz_items(GameMode.TEAM_QUIZ)
ITEMS[GameMode.TEAM_DUEL] = _quiz_items(GameMode.TEAM_DUEL)


def choose_quiz_pack(available: list[int], count: int, *, rng=None) -> list[int]:
    """Mix themes and randomize starts using the existing reviewed bank."""
    rng = rng or random.SystemRandom()
    categories: dict[str, list[int]] = {}
    for index in available:
        categories.setdefault(ITEMS[GameMode.SOLO_QUIZ][index].category, []).append(index)
    chosen = []
    while categories and len(chosen) < count:
        themes = list(categories)
        rng.shuffle(themes)
        for theme in themes:
            index = rng.choice(categories[theme])
            categories[theme].remove(index)
            chosen.append(index)
            if not categories[theme]:
                del categories[theme]
            if len(chosen) == count:
                break
    return chosen
ITEMS[GameMode.GUESS_COUNTRY] = _country_items()
ITEMS[GameMode.TRUE_OR_MYTH] = _truth_items()
ITEMS[GameMode.CULTURE] = _culture_items()
ITEMS[GameMode.ASSOCIATIONS] = _culture_items(associations=True)
ITEMS[GameMode.CHRONOLOGY] = _chronology_items()
ITEMS[GameMode.WORD_CHAIN] = _word_chain_items()
ITEMS[GameMode.LOGIC] = _logic_items()
ITEMS[GameMode.MEMORY] = _memory_items()


def items_for_mode(mode: GameMode) -> tuple[GameItem, ...]:
    """Return the offline, versioned content currently available for a mode."""
    return ITEMS.get(mode, ())
