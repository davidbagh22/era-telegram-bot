from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_postgres_is_private_without_replacing_existing_database():
    blueprint = yaml.safe_load((ROOT / 'render.yaml').read_text())
    database = next(item for item in blueprint['databases'] if item['name'] == 'era-postgres')
    assert database['ipAllowList'] == []
    assert (database['region'], database['databaseName'], database['user']) == (
        'frankfurt', 'era_nfvd', 'era')
    service = next(item for item in blueprint['services'] if item['name'] == 'era-telegram-bot')
    database_url = next(item for item in service['envVars'] if item['key'] == 'DATABASE_URL')
    assert database_url['fromDatabase'] == {'name': 'era-postgres', 'property': 'connectionString'}
    assert service['region'] == database['region']


def test_external_ci_uses_snapshot_api_not_production_database_ingress():
    backup = (ROOT / '.github/workflows/database-backup.yml').read_text()
    assert 'Download transient production snapshot using GitHub OIDC' in backup
    assert '${BACKUP_API_BASE}/snapshot' in backup
    assert 'BACKUP_DATABASE_URL' not in backup
    ci = (ROOT / '.github/workflows/ci.yml').read_text()
    assert 'DATABASE_URL: postgresql+asyncpg://era_test:era_test@127.0.0.1:5432/era_test' in ci
