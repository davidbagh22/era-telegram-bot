from app.services.recognition_catalog import RECOGNITION_CATALOG


def _by_key():
    return {(item["issuer"], item["title"]): item for item in RECOGNITION_CATALOG}


def test_recognition_catalog_contains_exactly_40_documents():
    assert len(RECOGNITION_CATALOG) == 40
    assert len(_by_key()) == 40


def test_catalog_uses_points_without_rank_requirements():
    for item in RECOGNITION_CATALOG:
        assert item["points"] > 0
        assert item["rank"] is None


def test_only_volunteering_degrees_require_extra_hours():
    expected = {
        ("Ассоциация студентов российских вузов в Армении", "Волонтёрская деятельность — III степень"): 20,
        ("Ассоциация студентов российских вузов в Армении", "Волонтёрская деятельность — II степень"): 40,
        ("Ассоциация студентов российских вузов в Армении", "Волонтёрская деятельность — I степень"): 80,
    }
    for key, item in _by_key().items():
        if key in expected:
            assert item["eligibility"] == {
                "required_metrics": {"volunteer_hours": expected[key]}
            }
        else:
            assert item["eligibility"] == {}


def test_key_thresholds_match_approved_catalog():
    items = _by_key()
    assert items[("ЭРА", "Сертификат участника ЭРА")]["points"] == 2000
    assert items[("ЭРА", "Активный участник ЭРА")]["points"] == 2000
    assert items[("ЭРА", "Рекомендательное письмо ЭРА")]["points"] == 5500
    assert items[("Дом Москвы в Ереване", "Сертификат Дома Москвы")]["points"] == 5000
    assert items[("Русский дом", "Сертификат Русского дома")]["points"] == 5000
    assert items[("КСООРС Армении", "Сертификат КСООРС")]["points"] == 5000
    assert items[("Ассоциация студентов российских вузов в Армении", "Сертификат АСРВВА")]["points"] == 5000
    assert items[("Дом Москвы в Ереване", "Благодарственное письмо «За вклад в развитие молодёжного сотрудничества»")]["points"] == 6000
    assert items[("КСООРС Армении", "За особый вклад в развитие молодёжного движения российских соотечественников в Армении")]["points"] == 8000
