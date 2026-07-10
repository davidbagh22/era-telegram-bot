from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.database.models import User
from app.handlers.participant.task_block2 import _approved, _task_menu
from app.utils import texts

router = Router(name="participant_task_reply")


@router.message(Command("tasks"), F.chat.type == "private")
async def tasks_command(message: Message, user: User | None, state: FSMContext) -> None:
    await state.clear()
    if not _approved(user):
        await message.answer(texts.APPLICATION_PENDING)
        return
    await message.answer("✅ Мои задачи\n\nВыберите раздел:", reply_markup=_task_menu())
