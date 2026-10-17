from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from scripts.upgrade_restored_database import validate_restore_target, validate_restored_heads


def test_restore_forward_migration_accepts_only_the_disposable_local_database():
    validate_restore_target('postgresql://restore:placeholder@localhost:5432/era_restore_check')
    for url in (
        'postgresql://restore:placeholder@production.example/era_restore_check',
        'postgresql://restore:placeholder@localhost/era',
        'sqlite:///era_restore_check',
    ):
        with pytest.raises(ValueError, match='isolated restore verifier'):
            validate_restore_target(url)


def test_known_previous_backup_schema_is_supported_but_unknown_revision_is_rejected():
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    script = ScriptDirectory.from_config(config)
    validate_restored_heads(script, ['0061_notification_message'])
    validate_restored_heads(script, script.get_heads())
    for heads in ([], ['future_unknown_revision'], ['0061_notification_message', 'future_unknown_revision']):
        with pytest.raises(ValueError, match='unsupported schema revision'):
            validate_restored_heads(script, heads)
