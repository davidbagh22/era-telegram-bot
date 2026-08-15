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
    input_type: str


@router.get("/questions", response_model=list[ProjectBuilderQuestionOut])
async def read_project_builder_questions() -> list[ProjectBuilderQuestionOut]:
    """Full participant project constructor, including date and time steps."""
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
