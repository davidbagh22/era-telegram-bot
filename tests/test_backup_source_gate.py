import pytest

from scripts.backup_source_gate import wait_for_backup_source


def test_source_is_actual_live_commit_even_for_an_old_workflow_rerun():
    calls = []
    def fetch(url):
        calls.append(url)
        return {'status': 'ok', 'commit': '27ff4ca'} if url.endswith('/health') else {'status': 'ready'}
    assert wait_for_backup_source('https://production.example/', fetch=fetch, attempts=1) == '27ff4ca'
    assert calls == ['https://production.example/health', 'https://production.example/ready']


@pytest.mark.parametrize('health,ready', [
    ({'status': 'error', 'commit': '27ff4ca'}, {'status': 'ready'}),
    ({'status': 'ok', 'commit': '27ff4ca'}, {'status': 'starting'}),
    ({'status': 'ok', 'commit': 'invalid\nvalue'}, {'status': 'ready'}),
    ({'status': 'ok'}, {'status': 'ready'}),
])
def test_source_gate_rejects_unhealthy_or_unidentified_production(health, ready):
    with pytest.raises(RuntimeError, match='healthy_production_backup_source_unavailable'):
        wait_for_backup_source('https://production.example', attempts=1,
                               fetch=lambda url: health if url.endswith('/health') else ready)


def test_source_gate_retries_transient_errors_and_is_bounded():
    sleeps = []
    health_attempts = []
    def fetch(url):
        if url.endswith('/ready'):
            return {'status': 'ready'}
        health_attempts.append(True)
        if len(health_attempts) < 2:
            raise OSError('temporarily unavailable')
        return {'status': 'ok', 'commit': '27ff4ca'}
    assert wait_for_backup_source('https://production.example', attempts=2, fetch=fetch, sleep=sleeps.append) == '27ff4ca'
    assert sleeps == [10] and len(health_attempts) == 2
