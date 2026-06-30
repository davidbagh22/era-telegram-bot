import json
import logging
from typing import Any

from openai import AsyncOpenAI, OpenAIError

from app.config import Settings

logger = logging.getLogger(__name__)

PROJECT_INSTRUCTIONS = """Вы — проектный методолог общественной организации «ЭРА».
На основе ответов участника оформите сильный, реалистичный проектный документ на русском языке.
Не выдумывайте факты. Если данных не хватает, помечайте предложение как рекомендацию.
Стиль живой, ясный и уверенный: без канцелярита, пафоса и политических формулировок.

Структура: название; краткое описание; актуальность; целевая аудитория; цель; 5–7 задач;
департамент и направление с объяснением; формат; программа с таймингом; команда; ресурсы;
роль ЭРА; измеримые результаты; 3–5 рисков и решения; три рекомендации; короткий анонс
для Telegram; итоговая оценка потенциала."""

EVENT_INSTRUCTIONS = """Вы — организатор мероприятий и проектный стратег ЭРА.
Создайте реалистичную концепцию молодёжного мероприятия на русском языке. Стиль живой,
простой и уважительный, без канцелярита, пафоса и политики. Структура: название, описание,
аудитория, департамент и направление, цель, формат, программа с таймингом, интерактив,
команда и роли, ресурсы, вовлечение участников, измеримый результат и анонс для Telegram."""

REPORT_INSTRUCTIONS = """Оформите данные в ясный отчёт ЭРА на русском языке. Отделите факты,
выводы, проблемы, рекомендации и следующие действия. Не придумывайте отсутствующие данные."""

PORTFOLIO_INSTRUCTIONS = """Составьте краткое профессиональное резюме участника ЭРА на русском
языке. Покажите реальные проекты, мероприятия, задачи, навыки и достижения. Не придумывайте факты."""


class AIUnavailableError(RuntimeError):
    pass


class AIService:
    def __init__(self, settings: Settings) -> None:
        self.model = settings.openai_model
        self.client = (
            AsyncOpenAI(api_key=settings.openai_api_key, timeout=60, max_retries=2)
            if settings.openai_api_key
            else None
        )

    @property
    def available(self) -> bool:
        return self.client is not None

    async def _generate(self, instructions: str, data: Any) -> str:
        if self.client is None:
            raise AIUnavailableError("OPENAI_API_KEY is not configured")
        try:
            response = await self.client.responses.create(
                model=self.model,
                instructions=instructions,
                input=json.dumps(data, ensure_ascii=False, default=str),
            )
            if not response.output_text:
                raise AIUnavailableError("The model returned an empty response")
            return response.output_text.strip()
        except OpenAIError as exc:
            logger.exception("OpenAI request failed")
            raise AIUnavailableError("OpenAI request failed") from exc

    async def generate_project(self, data: dict[str, Any]) -> str:
        return await self._generate(PROJECT_INSTRUCTIONS, data)

    async def improve_project(self, text: str, instruction: str) -> str:
        return await self._generate(
            PROJECT_INSTRUCTIONS,
            {"project": text, "revision_request": instruction},
        )

    async def generate_event_plan(self, data: dict[str, Any]) -> str:
        return await self._generate(EVENT_INSTRUCTIONS, data)

    async def generate_report(self, raw_data: dict[str, Any]) -> str:
        return await self._generate(REPORT_INSTRUCTIONS, raw_data)

    async def generate_portfolio_summary(self, user_data: dict[str, Any]) -> str:
        return await self._generate(PORTFOLIO_INSTRUCTIONS, user_data)


def fallback_project_document(data: dict[str, Any]) -> str:
    return f"""Проект: {data.get("idea", "Без названия")}

Краткое описание
{data.get("idea", "Не указано")}

Актуальность
{data.get("relevance", "Не указано")}

Целевая аудитория
{data.get("target_audience", "Не указано")}

Цель
{data.get("goal", "Не указано")}

Департамент и направление
{data.get("department", "Не определён")} — {data.get("direction", "Не определено")}

Формат
{data.get("format", "Не указан")}

Программа
{data.get("program", "Не указана")}

Команда
{data.get("team", "Не указана")}

Ресурсы
{data.get("resources", "Не указаны")}

Ожидаемый результат
{data.get("expected_result", "Не указан")}

Поддержка ЭРА
{data.get("needs_from_era", "Не указана")}

Черновик сформирован без ИИ. Его можно дополнить перед отправкой на рассмотрение."""
