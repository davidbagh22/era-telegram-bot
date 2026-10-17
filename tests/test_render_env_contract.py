"""Exercise the real environment loader against deployed Blueprint values."""
from pathlib import Path

import yaml

from app.config import Settings


def test_blueprint_report_audience_is_parseable_from_environment(monkeypatch):
    blueprint = yaml.safe_load(Path('render.yaml').read_text())
    service = next(item for item in blueprint['services'] if item['name'] == 'era-telegram-bot')
    values = {item['key']: str(item['value']) for item in service['envVars'] if 'value' in item}
    monkeypatch.setenv('MANAGEMENT_REPORT_RECIPIENT_IDS', values['MANAGEMENT_REPORT_RECIPIENT_IDS'])
    monkeypatch.setenv('FEATURE_MANAGEMENT_REPORTS', values['FEATURE_MANAGEMENT_REPORTS'])
    settings = Settings(bot_token='1234567890:test', _env_file=None)
    assert settings.management_report_recipient_ids == []
    assert settings.feature_management_reports == 'ALL'
