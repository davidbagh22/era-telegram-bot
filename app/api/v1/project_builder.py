from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, get_settings
from app.config import Settings
from app.database.models import User
from app.services.ai_service import AIService, AIUnavailableError
from app.services.project_builder import PROJECT_QUESTIONS

router = APIRouter(prefix="/project-builder", tags=["project-builder"])


class ProjectBuilderQuestionOut(BaseModel):
    key: str
    block: str
    title: str
    prompt: str
    ai_hint: str | None
    input_type: str


class ProjectAnswerAssistIn(BaseModel):
    question_key: str = Field(min_length=1, max_length=100)
    answer: str = Field(min_length=1, max_length=8000)
    operation: Literal["formulate", "shorten", "improve"]


class ProjectAnswerAssistOut(BaseModel):
    text: str


@router.get("/questions", response_model=list[ProjectBuilderQuestionOut])
async def read_project_builder_questions() -> list[ProjectBuilderQuestionOut]:
    return [
        ProjectBuilderQuestionOut(
            key=question.key,
            block=question.block,
            title=question.title,
            prompt=question.prompt,
            ai_hint=question.ai_hint,
            input_type=question.input_type,
        )
        for question in PROJECT_QUESTIONS
    ]


@router.post("/assist", response_model=ProjectAnswerAssistOut)
async def assist_project_answer(
    payload: ProjectAnswerAssistIn,
    _user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ProjectAnswerAssistOut:
    question = next(
        (item for item in PROJECT_QUESTIONS if item.key == payload.question_key),
        None,
    )
    if question is None:
        raise HTTPException(status_code=404, detail="project_question_not_found")
    service = AIService(settings)
    try:
        text = await service.assist_project_answer(
            question=question.prompt,
            answer=payload.answer.strip(),
            operation=payload.operation,
        )
    except AIUnavailableError as exc:
        raise HTTPException(status_code=503, detail="ai_unavailable") from exc
    return ProjectAnswerAssistOut(text=text)
