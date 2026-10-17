"""Forward-migration check on the disposable backup verifier, never production."""
import os

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url


def validate_restore_target(url):
    parsed = make_url(url)
    if (parsed.get_backend_name() != 'postgresql' or parsed.host not in {'localhost', '127.0.0.1', '::1'}
            or parsed.database != 'era_restore_check'):
        raise ValueError('Forward migration is restricted to the isolated restore verifier')


def validate_restored_heads(script, restored_heads):
    supported = {revision.revision for revision in script.walk_revisions()}
    if not restored_heads or not set(restored_heads).issubset(supported):
        raise ValueError('Backup has an empty or unsupported schema revision')


def main():
    url = os.environ['RESTORE_DATABASE_URL']
    validate_restore_target(url)
    config = Config('alembic.ini')
    script = ScriptDirectory.from_config(config)
    validate_restored_heads(script, os.environ['RESTORED_HEADS'].split())
    os.environ['DATABASE_URL'] = url
    os.environ['BOT_TOKEN'] = '0000000000:ISOLATEDRESTOREMIGRATION'
    command.upgrade(config, 'heads')
    print('Forward migration on the isolated restored database completed')


if __name__ == '__main__':
    main()
