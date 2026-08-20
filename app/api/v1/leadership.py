from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_bot, get_session, get_settings
from app.api.v1.leader import require_leader
from app.config import Settings
from app.database.leadership_models import LeadershipFeedback
from app.database.models import LeadershipAttentionItem, LeadershipGoal, LeadershipReport, Task, User
from app.services import (
    leader_service,
    leadership_goal_service,
    leadership_report_service,
    leadership_weekly_service,
)
from app.services.leadership_permission_service import active_office_assignments
from app.utils.constants import TaskStatus

router = APIRouter(prefix="/leadership", tags=["leadership"])


class OfficeAssignmentSummaryOut(BaseModel):
    id: int
