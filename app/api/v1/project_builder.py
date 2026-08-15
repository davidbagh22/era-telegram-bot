from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.project_builder import PROJECT_QUESTIONS

router = APIRouter(prefix="/project-builder", tags=["project-builder"])


class ProjectBuilderQuestionOut(BaseModel):
    key: str
    block: str
    title: str
    prompt: str
    ai_hint: str | None


@router.get("/questions", response_model=list[ProjectBuilderQuestionOut])
async def read_project_builder_questions() -> list[ProjectBuilderQuestionOut]:
    """Participant-facing editorial guidance for the Mini App constructor.

    The existing project API intentionally exposes only editable text fields;
    keep the same rule here while additionally returning each curated AI prompt.
    """
    return [
        ProjectBuilderQuestionOut(
            key=question.key,
            block=question.block,
            title=question.title,
            prompt=question.prompt,
            ai_hint=question.ai_hint,
        )
        for question in PROJECT_QUESTIONS
        if question.input_type == "text"
    ]
