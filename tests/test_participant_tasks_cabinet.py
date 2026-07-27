import inspect

from app.handlers.participant import task_block2


def _callbacks(keyboard) -> set[str]:
    return {
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    }


def test_task_cabinet_has_separate_open_tasks_section() -> None:
    callbacks = _callbacks(task_block2._task_menu())

    assert "tasks:list:active" in callbacks
    assert "tasks:list:open" in callbacks
    assert "tasks:list:archive" in callbacks


def test_active_task_handler_supports_open_tasks_mode() -> None:
    source = inspect.getsource(task_block2)

    assert '"tasks:list:open"' in source
    assert 'task.task_type == "challenge"' in source
    assert 'task.status == "published"' in source
    assert "joined_ids" in source
    assert "_matches_task_audience" in source


def test_participant_task_router_owns_join_view_and_result() -> None:
    source = inspect.getsource(task_block2)

    assert 'F.data.startswith("task:join:")' in source
    assert 'F.data.startswith("task:view:")' in source
    assert 'F.data.startswith("task:result:")' in source
