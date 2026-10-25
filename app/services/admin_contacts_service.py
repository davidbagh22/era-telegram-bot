"""Organization-contacts CRUD — shared by the bot's "🤝 База организаций"
flow (app/handlers/admin/management_ready.py) and the Mini App's admin
tools. See app/services/admin_goals_service.py for why this is extracted.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.management_models import OrganizationContact


class ContactError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(slots=True)
class ContactOut:
    id: int
    organization_name: str
    contact_name: str | None
    position: str | None
    second_contact_name: str | None
    second_position: str | None
    email: str | None
    phone: str | None
    notes: str | None


def _to_out(contact: OrganizationContact) -> ContactOut:
    return ContactOut(
        id=contact.id,
        organization_name=contact.organization_name,
        contact_name=contact.contact_name,
        position=contact.position,
        second_contact_name=contact.second_contact_name,
        second_position=contact.second_position,
        email=contact.email,
        phone=contact.phone,
        notes=contact.notes,
    )


async def list_contacts(session: AsyncSession) -> list[ContactOut]:
    contacts = (
        await session.scalars(
            select(OrganizationContact)
            .where(OrganizationContact.is_active.is_(True))
            .order_by(OrganizationContact.organization_name)
            .limit(100)
        )
    ).all()
    return [_to_out(contact) for contact in contacts]


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()[:500]
    return value or None


async def create_contact(
    session: AsyncSession,
    *,
    organization_name: str,
    contact_name: str | None = None,
    position: str | None = None,
    second_contact_name: str | None = None,
    second_position: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    notes: str | None = None,
    created_by: int | None,
) -> OrganizationContact:
    name = _clean(organization_name)
    if not name:
        raise ContactError("organization_name_required")
    contact = OrganizationContact(
        organization_name=name,
        contact_name=_clean(contact_name),
        position=_clean(position),
        second_contact_name=_clean(second_contact_name),
        second_position=_clean(second_position),
        email=_clean(email),
        phone=_clean(phone),
        notes=_clean(notes),
        created_by=created_by,
    )
    session.add(contact)
    await session.flush()
    return contact


async def archive_contact(session: AsyncSession, contact_id: int) -> OrganizationContact:
    contact = await session.get(OrganizationContact, contact_id)
    if contact is None:
        raise ContactError("contact_not_found")
    contact.is_active = False
    await session.flush()
    return contact
