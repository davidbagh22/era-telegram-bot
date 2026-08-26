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
    input_type: str


@router.get("/questions", response_model=list[ProjectBuilderQuestionOut])
async def read_project_builder_questions() -> list[ProjectBuilderQuestionOut]:
    return [
        ProjectBuilderQuestionOut(
            key=question.key,
            block=question.block,
            title=question.title,
            prompt=question.prompt,
            input_type=question.input_type,
        )
        for question in PROJECT_QUESTIONS
    ]
