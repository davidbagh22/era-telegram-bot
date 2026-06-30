from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class RegistrationRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    age: int = Field(ge=14, le=100)
    phone: str = Field(min_length=7, max_length=32)
    city: str = Field(min_length=1, max_length=100)
    education_work: str = Field(min_length=1, max_length=255)
    occupation: str = Field(min_length=1, max_length=1000)
    departments: list[str] = Field(default_factory=list, max_length=2)
    directions: list[str] = Field(default_factory=list, max_length=6)
    available_time: str = Field(min_length=1, max_length=100)
    skills: list[str] = Field(min_length=1, max_length=12)
    experience: str = Field(min_length=1, max_length=1500)
    desired_path: str = Field(min_length=1, max_length=100)
    motivation: str = Field(min_length=1, max_length=1500)
    personal_data_consent: bool

    @field_validator("personal_data_consent")
    @classmethod
    def require_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Consent is required")
        return value


class ProjectCreateRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=2000)
    department: str = Field(min_length=1, max_length=100)
    direction: str = Field(min_length=1, max_length=100)
    target_audience: str = Field(min_length=1, max_length=500)
    relevance: str = Field(min_length=1, max_length=3000)
    goal: str = Field(min_length=1, max_length=2000)
    format: str = Field(min_length=1, max_length=100)
    program: str = Field(min_length=1, max_length=3000)
    resources: str = Field(min_length=1, max_length=3000)
    team: str = Field(min_length=1, max_length=3000)
    expected_result: str = Field(min_length=1, max_length=3000)
    needs_from_era: str = Field(min_length=1, max_length=3000)
    use_ai: bool = True


class QuestionCreateRequest(BaseModel):
    text: str = Field(min_length=3, max_length=3000)


class TaskStatusRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in {"in_progress", "review"}:
            raise ValueError("Unsupported task status")
        return value
