"""Department structure editor — shared by the bot's "🏛 Редактор структуры"
flow (app/handlers/admin/management_ready.py) and the Mini App's admin
tools. Only Department.description is editable through this flow, matching
the bot's existing scope (Direction.description exists on the model but was
never exposed here — preserved intentionally, not an oversight).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Department


class StructureError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(slots=True)
class DepartmentOut:
    id: int
    name: str
    description: str | None


async def list_departments(session: AsyncSession) -> list[DepartmentOut]:
    departments = (await session.scalars(select(Department).order_by(Department.name))).all()
    return [DepartmentOut(id=d.id, name=d.name, description=d.description) for d in departments]


async def update_department_description(
    session: AsyncSession, department_id: int, description: str
) -> Department:
    department = await session.get(Department, department_id)
    if department is None:
        raise StructureError("department_not_found")
    department.description = description.strip()[:3000]
    await session.flush()
    return department
