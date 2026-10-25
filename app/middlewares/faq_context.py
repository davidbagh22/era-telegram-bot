"""Observe existing FAQ action callbacks without introducing dispatch aliases."""

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from app.content.era_faq import FAQ_ACTIONS, FAQ_TOPICS, faq_message_context
from app.services.audit_service import audit
from app.utils import texts
from app.utils.constants import ApplicationStatus


class FaqContextMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if (
            not isinstance(event, CallbackQuery)
            or not isinstance(event.message, Message)
            or event.message.chat.type != "private"
        ):
            return await handler(event, data)
        context = faq_message_context(event.message.text)
        if not context:
            return await handler(event, data)
        action = context.get("action")
        target = FAQ_ACTIONS.get(action, (None, None))[1]
        is_contact = event.data in {"contact:menu", "question:start"}
        if not is_contact and (not target or event.data != target):
            return await handler(event, data)
        user = data.get("user")
        if (
            not user
            or user.application_status != ApplicationStatus.APPROVED
            or user.is_blocked
            or user.is_archived
        ):
            await event.answer(texts.APPLICATION_PENDING, show_alert=True)
            return None
        context = {
            **context,
            "topic": FAQ_TOPICS.get(action) if event.data == "question:start" else None,
        }
        data["faq_context"] = context
        details = {
            "user_id": user.id,
            "category": context["category"],
            "question": context["question"],
            "action": action if event.data == target else "contact",
        }
        if is_contact:
            await audit(
                data["session"],
                actor_id=user.id,
                action="faq_contact_clicked",
                entity_type="faq",
                new_value=details,
            )
        if event.data == target:
            await audit(
                data["session"],
                actor_id=user.id,
                action="faq_action_clicked",
                entity_type="faq",
                new_value=details,
            )
        return await handler(event, data)
