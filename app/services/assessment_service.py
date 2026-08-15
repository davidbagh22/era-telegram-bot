from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from statistics import mean
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.development_models import (
    AssessmentAnswer,
    AssessmentDefinition,
    AssessmentOption,
    AssessmentQuestion,
    AssessmentScale,
    AssessmentScore,
    AssessmentScoringRule,
    AssessmentSession,
    AssessmentVersion,
    UserVectorProfile,
)
from app.database.models import User
from app.services.assessment_catalog import ASSESSMENT_BY_CODE, ASSESSMENTS, STRENGTHS_DEFINITION


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _definition_values(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": item["title"],
        "description": item["description"],
        "source": item["source"],
        "methodology": item["methodology"],
        "license": item["license"],
        "license_status": item["license_status"],
        "estimated_minutes": item["estimated_minutes"],
        "min_age": item["min_age"],
        "recommended_retake_after_days": item["retake"],
        "construct_type": item["construct"],
        "active": True,
    }


async def _upsert_definition(session: AsyncSession, item: dict[str, Any]) -> AssessmentDefinition:
    row = await session.scalar(select(AssessmentDefinition).where(AssessmentDefinition.code == item["code"]))
    if row is None:
        row = AssessmentDefinition(code=item["code"], **_definition_values(item))
        session.add(row)
        await session.flush()
        return row
    for field, value in _definition_values(item).items():
        setattr(row, field, value)
    return row


async def ensure_catalog(session: AsyncSession) -> None:
    """Idempotently seeds the exact versions, questions and scoring rules used in production."""
    for item in [*ASSESSMENTS, STRENGTHS_DEFINITION]:
        definition = await _upsert_definition(session, item)
        if item["code"] == STRENGTHS_DEFINITION["code"]:
            continue

        version = await session.scalar(
            select(AssessmentVersion).where(
                AssessmentVersion.definition_id == definition.id,
                AssessmentVersion.version == item["version"],
            )
        )
        response_scale = {"options": item["response_scale"]}
        if version is None:
            version = AssessmentVersion(
                definition_id=definition.id,
                version=item["version"],
                language=item["language"],
                translation_source=item["translation_source"],
                response_scale_json=response_scale,
                interpretation_constraints_json=item["constraints"],
                scoring_notes="Deterministic scoring from catalog; no AI-generated score or diagnosis.",
                active=True,
            )
            session.add(version)
            await session.flush()
        else:
            version.language = item["language"]
            version.translation_source = item["translation_source"]
            version.response_scale_json = response_scale
            version.interpretation_constraints_json = item["constraints"]
            version.scoring_notes = "Deterministic scoring from catalog; no AI-generated score or diagnosis."
            version.active = True

        existing_scales = {
            row.code: row
            for row in (
                await session.scalars(select(AssessmentScale).where(AssessmentScale.version_id == version.id))
            ).all()
        }
        for scale in item["scales"]:
            row = existing_scales.get(scale["code"])
            if row is None:
                row = AssessmentScale(version_id=version.id, code=scale["code"], title=scale["title"])
                session.add(row)
            else:
                row.title = scale["title"]

        rules = {
            row.scale_code: row
            for row in (
                await session.scalars(
                    select(AssessmentScoringRule).where(AssessmentScoringRule.version_id == version.id)
                )
            ).all()
        }
        for scale_code, rule in item["scoring"].items():
            row = rules.get(scale_code)
            if row is None:
                session.add(
                    AssessmentScoringRule(version_id=version.id, scale_code=scale_code, rule_json=rule)
                )
            else:
                row.rule_json = rule

        existing_questions = {
            row.code: row
            for row in (
                await session.scalars(
                    select(AssessmentQuestion).where(AssessmentQuestion.version_id == version.id)
                )
            ).all()
        }
        for position, question in enumerate(item["questions"], start=1):
            row = existing_questions.get(question["code"])
            if row is None:
                row = AssessmentQuestion(
                    version_id=version.id,
                    code=question["code"],
                    text=question["text"],
                    position=position,
                    scale_code=question["scale"],
                    reverse_keyed=bool(question.get("reverse")),
                )
                session.add(row)
                await session.flush()
            else:
                row.text = question["text"]
                row.position = position
                row.scale_code = question["scale"]
                row.reverse_keyed = bool(question.get("reverse"))

            existing_options = {
                option.value: option
                for option in (
                    await session.scalars(
                        select(AssessmentOption).where(AssessmentOption.question_id == row.id)
                    )
                ).all()
            }
            for option_position, option in enumerate(item["response_scale"], start=1):
                option_row = existing_options.get(option["value"])
                if option_row is None:
                    session.add(
                        AssessmentOption(
                            question_id=row.id,
                            value=option["value"],
                            label=option["label"],
                            position=option_position,
                        )
                    )
                else:
                    option_row.label = option["label"]
                    option_row.position = option_position

    await session.flush()


async def _active_version(session: AsyncSession, definition_id: int) -> AssessmentVersion | None:
    return await session.scalar(
        select(AssessmentVersion)
        .where(AssessmentVersion.definition_id == definition_id, AssessmentVersion.active.is_(True))
        .order_by(desc(AssessmentVersion.id))
    )


async def get_definition(session: AsyncSession, code: str) -> AssessmentDefinition | None:
    await ensure_catalog(session)
    return await session.scalar(select(AssessmentDefinition).where(AssessmentDefinition.code == code))


async def latest_result(session: AsyncSession, user_id: int, definition_id: int) -> dict[str, Any] | None:
    version_ids = select(AssessmentVersion.id).where(AssessmentVersion.definition_id == definition_id)
    completed = await session.scalar(
        select(AssessmentSession)
        .where(
            AssessmentSession.user_id == user_id,
            AssessmentSession.version_id.in_(version_ids),
            AssessmentSession.status == "completed",
        )
        .order_by(desc(AssessmentSession.completed_at), desc(AssessmentSession.id))
    )
    if completed is None:
        return None
    return await result_payload(session, completed)


async def definition_payload(
    session: AsyncSession,
    definition: AssessmentDefinition,
    *,
    user_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "code": definition.code,
        "title": definition.title,
        "description": definition.description,
        "source": definition.source,
        "methodology": definition.methodology,
        "license": definition.license,
        "license_status": definition.license_status,
        "estimated_minutes": definition.estimated_minutes,
        "min_age": definition.min_age,
        "recommended_retake_after_days": definition.recommended_retake_after_days,
        "construct_type": definition.construct_type,
        "available": definition.license_status in {"approved", "available_after_data"},
    }
    if definition.code == STRENGTHS_DEFINITION["code"]:
        payload["version"] = None
        payload["question_count"] = 0
        payload["notice"] = "Сильные стороны собираются из уже пройденных исследований, а не из отдельного теста."
    else:
        version = await _active_version(session, definition.id)
        if version is not None:
            payload["version"] = version.version
            payload["language"] = version.language
            payload["translation_source"] = version.translation_source
            payload["notice"] = (version.interpretation_constraints_json or {}).get("notice")
            payload["validation_note"] = (version.interpretation_constraints_json or {}).get("validation")
            payload["question_count"] = len(
                (
                    await session.scalars(
                        select(AssessmentQuestion.id).where(AssessmentQuestion.version_id == version.id)
                    )
                ).all()
            )
    if user_id is not None:
        payload["last_result"] = await latest_result(session, user_id, definition.id)
    return payload


def _user_age(user: User) -> int | None:
    if user.birth_date:
        today = date.today()
        return today.year - user.birth_date.year - (
            (today.month, today.day) < (user.birth_date.month, user.birth_date.day)
        )
    return user.age


async def _session_payload(session: AsyncSession, row: AssessmentSession) -> dict[str, Any]:
    version = await session.get(AssessmentVersion, row.version_id)
    if version is None:
        raise ValueError("assessment_version_not_found")
    definition = await session.get(AssessmentDefinition, version.definition_id)
    if definition is None:
        raise ValueError("assessment_definition_not_found")

    questions = list(
        (
            await session.scalars(
                select(AssessmentQuestion)
                .where(AssessmentQuestion.version_id == version.id)
                .order_by(AssessmentQuestion.position)
            )
        ).all()
    )
    answers = {
        answer.question_code: answer.value_json
        for answer in (
            await session.scalars(select(AssessmentAnswer).where(AssessmentAnswer.session_id == row.id))
        ).all()
    }
    question_payloads: list[dict[str, Any]] = []
    for question in questions:
        options = list(
            (
                await session.scalars(
                    select(AssessmentOption)
                    .where(AssessmentOption.question_id == question.id)
                    .order_by(AssessmentOption.position)
                )
            ).all()
        )
        question_payloads.append(
            {
                "code": question.code,
                "text": question.text,
                "position": question.position,
                "scale_code": question.scale_code,
                "options": [{"value": option.value, "label": option.label} for option in options],
            }
        )
    return {
        "id": row.id,
        "assessment_code": definition.code,
        "title": definition.title,
        "version": version.version,
        "status": row.status,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "questions": question_payloads,
        "answers": answers,
        "answered_count": len(answers),
        "question_count": len(questions),
        "notice": (version.interpretation_constraints_json or {}).get("notice"),
    }


async def start_assessment(session: AsyncSession, user: User, code: str) -> dict[str, Any]:
    definition = await get_definition(session, code)
    if definition is None:
        raise ValueError("assessment_not_found")
    if definition.code == STRENGTHS_DEFINITION["code"]:
        raise ValueError("assessment_is_derived")
    if definition.license_status != "approved":
        raise ValueError("assessment_methodology_not_approved")

    age = _user_age(user)
    if definition.min_age is not None and age is not None and age < definition.min_age:
        raise ValueError("assessment_age_restricted")

    version = await _active_version(session, definition.id)
    if version is None:
        raise ValueError("assessment_version_not_seeded")

    in_progress = await session.scalar(
        select(AssessmentSession)
        .where(
            AssessmentSession.user_id == user.id,
            AssessmentSession.version_id == version.id,
            AssessmentSession.status == "in_progress",
        )
        .order_by(desc(AssessmentSession.id))
    )
    if in_progress is None:
        in_progress = AssessmentSession(
            user_id=user.id,
            version_id=version.id,
            status="in_progress",
            started_at=utcnow(),
            validity_status="preliminary",
            context_json={"source": "miniapp"},
        )
        session.add(in_progress)
        await session.flush()
    return await _session_payload(session, in_progress)


async def get_session_payload(
    session: AsyncSession, user_id: int, assessment_session_id: int
) -> dict[str, Any]:
    row = await session.get(AssessmentSession, assessment_session_id)
    if row is None or row.user_id != user_id:
        raise ValueError("assessment_session_not_found")
    return await _session_payload(session, row)


async def save_answer(
    session: AsyncSession,
    user_id: int,
    assessment_session_id: int,
    question_code: str,
    value: int,
) -> dict[str, Any]:
    row = await session.get(AssessmentSession, assessment_session_id)
    if row is None or row.user_id != user_id:
        raise ValueError("assessment_session_not_found")
    if row.status != "in_progress":
        raise ValueError("assessment_session_completed")

    question = await session.scalar(
        select(AssessmentQuestion).where(
            AssessmentQuestion.version_id == row.version_id,
            AssessmentQuestion.code == question_code,
        )
    )
    if question is None:
        raise ValueError("assessment_question_not_found")
    valid_values = set(
        (
            await session.scalars(
                select(AssessmentOption.value).where(AssessmentOption.question_id == question.id)
            )
        ).all()
    )
    if value not in valid_values:
        raise ValueError("assessment_answer_invalid")

    answer = await session.scalar(
        select(AssessmentAnswer).where(
            AssessmentAnswer.session_id == row.id,
            AssessmentAnswer.question_code == question_code,
        )
    )
    if answer is None:
        session.add(
            AssessmentAnswer(session_id=row.id, question_code=question_code, value_json=value)
        )
    else:
        answer.value_json = value
    await session.flush()
    return await _session_payload(session, row)


def score_scale(values: list[tuple[int, bool]], rule: dict[str, Any]) -> tuple[float, float]:
    if not values:
        raise ValueError("assessment_scale_empty")
    minimum = float(rule["min"])
    maximum = float(rule["max"])
    method = rule["method"]

    adjusted: list[float] = []
    if method == "mean_reverse":
        for value, reverse in values:
            adjusted.append((minimum + maximum - value) if reverse else float(value))
        raw = mean(adjusted)
    elif method == "mean":
        raw = mean(float(value) for value, _ in values)
    elif method == "sum":
        raw = sum(float(value) for value, _ in values)
    elif method == "sum_times":
        raw = sum(float(value) for value, _ in values) * float(rule.get("factor", 1))
    else:
        raise ValueError("assessment_scoring_method_unknown")

    normalized = 0.0 if maximum == minimum else ((raw - minimum) / (maximum - minimum)) * 100
    return round(raw, 2), round(max(0.0, min(100.0, normalized)), 1)


def _score_interpretation(code: str, scores: dict[str, dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(scores.items(), key=lambda item: item[1]["normalized"], reverse=True)
    if code == "WHO5_RU":
        score = scores["wellbeing"]["normalized"]
        return {
            "title": "Твоё самочувствие сейчас",
            "summary": f"Индекс благополучия за последние две недели: {round(score)} из 100.",
            "note": "Смотри прежде всего на динамику относительно себя. Один результат не является диагнозом.",
        }
    if code == "GSE_RU":
        raw = scores["self_efficacy"]["raw"]
        return {
            "title": "Ощущение собственной эффективности",
            "summary": f"Сумма по шкале: {round(raw)} из 40.",
            "note": "Это то, насколько уверенно ты сейчас воспринимаешь свою способность находить решения, а не измерение реальных способностей.",
        }
    if code in {"IPIP_BIG5_RU", "IPIP_FOLLOW_THROUGH_RU", "IPIP_SOCIAL_RU", "IPIP_NEWNESS_RU", "IPIP_INTERACTION_RU"}:
        labels = {
            "extraversion": "проявленность среди людей",
            "agreeableness": "ориентация на людей",
            "conscientiousness": "организованность и доведение",
            "emotional_stability": "эмоциональная устойчивость",
            "intellect": "интеллект и воображение",
        }
        top = [labels.get(scale, scale) for scale, _ in ordered[:2]]
        return {
            "title": "Твой профиль черт",
            "summary": "Наиболее выражены относительно остальных частей твоего профиля: " + ", ".join(top) + ".",
            "note": "Здесь нет лучшего или худшего профиля. Черты описывают привычные тенденции, а не ограничивают тебя.",
        }
    if code == "ERA_RIASEC_RU":
        labels = {
            "R": "практическое",
            "I": "исследовательское",
            "A": "творческое",
            "S": "социальное",
            "E": "предпринимательское",
            "C": "организационное",
        }
        top_codes = [scale for scale, _ in ordered[:3]]
        return {
            "title": "Карта интересов",
            "summary": f"Твой текущий код интересов: {'–'.join(top_codes)}. Сильнее всего притягивают направления: " + ", ".join(labels[code] for code in top_codes) + ".",
            "note": "Интерес — не способность и не профессия. Это подсказка, какие форматы деятельности стоит чаще пробовать.",
        }
    if code == "ERA_NEEDS_RU":
        labels = {
            "autonomy": "самостоятельность",
            "competence": "ощущение компетентности",
            "relatedness": "связь с людьми",
        }
        strongest = ordered[0][0]
        weakest = ordered[-1][0]
        return {
            "title": "Что сейчас поддерживает и чего может не хватать",
            "summary": f"Больше опоры сейчас даёт {labels[strongest]}, а больше внимания может требовать {labels[weakest]}.",
            "note": "Это текущий рефлексивный снимок, а не постоянная характеристика и не диагноз.",
        }
    return {
        "title": "Результат",
        "summary": "Результат сохранён в твоём профиле развития.",
        "note": "Сравнивай результат прежде всего с собой, а не с другими участниками.",
    }


async def _update_profile(
    session: AsyncSession,
    user_id: int,
    code: str,
    scores: dict[str, dict[str, Any]],
) -> None:
    profile = await session.get(UserVectorProfile, user_id)
    if profile is None:
        profile = UserVectorProfile(user_id=user_id)
        session.add(profile)
        await session.flush()

    normalized = {scale: round(data["normalized"]) for scale, data in scores.items()}
    if code == "WHO5_RU":
        state = dict(profile.state_json or {})
        state["who5_wellbeing"] = normalized["wellbeing"]
        profile.state_json = state
    elif code == "GSE_RU":
        traits = dict(profile.traits_json or {})
        traits["self_efficacy"] = normalized["self_efficacy"]
        profile.traits_json = traits
    elif code == "IPIP_BIG5_RU":
        traits = dict(profile.traits_json or {})
        traits["big5"] = normalized
        profile.traits_json = traits
    elif code.startswith("IPIP_"):
        traits = dict(profile.traits_json or {})
        focused = dict(traits.get("focused", {}))
        focused[code] = normalized
        traits["focused"] = focused
        profile.traits_json = traits
    elif code == "ERA_RIASEC_RU":
        ordered = sorted(normalized.items(), key=lambda item: item[1], reverse=True)
        profile.interests_json = {
            "riasec": normalized,
            "top_code": [scale for scale, _ in ordered[:3]],
            "methodology_version": "ERA-RIASEC-RU-V1-2026",
        }
    elif code == "ERA_NEEDS_RU":
        profile.needs_json = {
            "basic_needs": normalized,
            "methodology_version": "ERA-BASIC-NEEDS-RU-V1-2026",
        }
    profile.strengths_json = strengths_synthesis(profile)


def strengths_synthesis(profile: UserVectorProfile) -> list[str]:
    traits = dict(profile.traits_json or {})
    big5 = traits.get("big5")
    if not isinstance(big5, dict) or len(big5) < 2:
        return []
    labels = {
        "extraversion": "легче проявляться и вступать во взаимодействие",
        "agreeableness": "замечать людей и строить сотрудничество",
        "conscientiousness": "организовывать и доводить дела",
        "emotional_stability": "сохранять внутреннюю устойчивость",
        "intellect": "работать с идеями и воображением",
    }
    ordered = sorted(big5.items(), key=lambda item: float(item[1]), reverse=True)
    return [labels[scale] for scale, _ in ordered[:2] if scale in labels]


async def complete_assessment(
    session: AsyncSession, user_id: int, assessment_session_id: int
) -> dict[str, Any]:
    row = await session.get(AssessmentSession, assessment_session_id)
    if row is None or row.user_id != user_id:
        raise ValueError("assessment_session_not_found")
    if row.status == "completed":
        return await result_payload(session, row)

    version = await session.get(AssessmentVersion, row.version_id)
    if version is None:
        raise ValueError("assessment_version_not_found")
    definition = await session.get(AssessmentDefinition, version.definition_id)
    if definition is None:
        raise ValueError("assessment_definition_not_found")

    questions = list(
        (
            await session.scalars(
                select(AssessmentQuestion)
                .where(AssessmentQuestion.version_id == version.id)
                .order_by(AssessmentQuestion.position)
            )
        ).all()
    )
    answer_rows = list(
        (
            await session.scalars(select(AssessmentAnswer).where(AssessmentAnswer.session_id == row.id))
        ).all()
    )
    answers = {answer.question_code: answer.value_json for answer in answer_rows}
    if any(question.code not in answers for question in questions):
        raise ValueError("assessment_incomplete")

    grouped: dict[str, list[tuple[int, bool]]] = defaultdict(list)
    for question in questions:
        value = answers[question.code]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("assessment_answer_invalid")
        grouped[question.scale_code or "total"].append((value, question.reverse_keyed))

    rules = {
        rule.scale_code: rule
        for rule in (
            await session.scalars(
                select(AssessmentScoringRule).where(AssessmentScoringRule.version_id == version.id)
            )
        ).all()
    }
    score_payload: dict[str, dict[str, Any]] = {}
    for scale_code, values in grouped.items():
        rule = rules.get(scale_code)
        if rule is None:
            raise ValueError("assessment_scoring_rule_missing")
        raw, normalized = score_scale(values, rule.rule_json or {})
        score_payload[scale_code] = {"raw": raw, "normalized": normalized}
        score_row = await session.scalar(
            select(AssessmentScore).where(
                AssessmentScore.session_id == row.id,
                AssessmentScore.scale_code == scale_code,
            )
        )
        if score_row is None:
            session.add(
                AssessmentScore(
                    session_id=row.id,
                    scale_code=scale_code,
                    raw_score=raw,
                    normalized_score=normalized,
                    methodology_version=version.version,
                )
            )
        else:
            score_row.raw_score = raw
            score_row.normalized_score = normalized
            score_row.methodology_version = version.version

    row.status = "completed"
    row.validity_status = "complete"
    row.completed_at = utcnow()
    await _update_profile(session, user_id, definition.code, score_payload)
    await session.flush()
    return {
        "session_id": row.id,
        "assessment_code": definition.code,
        "title": definition.title,
        "version": version.version,
        "completed_at": row.completed_at,
        "scores": score_payload,
        "interpretation": _score_interpretation(definition.code, score_payload),
        "notice": (version.interpretation_constraints_json or {}).get("notice"),
    }


async def result_payload(session: AsyncSession, row: AssessmentSession) -> dict[str, Any]:
    version = await session.get(AssessmentVersion, row.version_id)
    if version is None:
        raise ValueError("assessment_version_not_found")
    definition = await session.get(AssessmentDefinition, version.definition_id)
    if definition is None:
        raise ValueError("assessment_definition_not_found")
    scores = {
        score.scale_code: {
            "raw": score.raw_score,
            "normalized": score.normalized_score,
        }
        for score in (
            await session.scalars(select(AssessmentScore).where(AssessmentScore.session_id == row.id))
        ).all()
    }
    return {
        "session_id": row.id,
        "assessment_code": definition.code,
        "title": definition.title,
        "version": version.version,
        "completed_at": row.completed_at,
        "scores": scores,
        "interpretation": _score_interpretation(definition.code, scores) if scores else None,
        "notice": (version.interpretation_constraints_json or {}).get("notice"),
    }


async def strengths_payload(session: AsyncSession, user_id: int) -> dict[str, Any]:
    profile = await session.get(UserVectorProfile, user_id)
    strengths = strengths_synthesis(profile) if profile is not None else []
    interests = dict(profile.interests_json or {}) if profile is not None else {}
    return {
        "code": STRENGTHS_DEFINITION["code"],
        "title": STRENGTHS_DEFINITION["title"],
        "description": STRENGTHS_DEFINITION["description"],
        "source": STRENGTHS_DEFINITION["source"],
        "methodology": STRENGTHS_DEFINITION["methodology"],
        "license": STRENGTHS_DEFINITION["license"],
        "license_status": STRENGTHS_DEFINITION["license_status"],
        "estimated_minutes": 0,
        "min_age": None,
        "recommended_retake_after_days": 30,
        "construct_type": "derived",
        "available": bool(strengths),
        "version": "ERA-STRENGTHS-SYNTHESIS-V1",
        "question_count": 0,
        "strengths": strengths,
        "interest_code": interests.get("top_code", []),
        "notice": "Сильные стороны здесь — осторожный синтез выраженных черт. Интересы не выдаются за способности.",
        "last_result": None,
    }
