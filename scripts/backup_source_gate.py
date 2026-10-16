"""Back up the healthy running production, including reruns of older workflows."""
import json
import re
import sys
import time
from urllib.request import urlopen


def read_json(url):
    with urlopen(url, timeout=10) as response:
        if response.status != 200:
            raise ValueError('source_unhealthy')
        return json.loads(response.read(4096))


def wait_for_backup_source(base_url, *, fetch=read_json, sleep=time.sleep, attempts=60):
    for attempt in range(attempts):
        try:
            health = fetch(base_url.rstrip('/') + '/health')
            ready = fetch(base_url.rstrip('/') + '/ready')
            commit = health.get('commit', '')
            if (health.get('status') == 'ok' and ready.get('status') == 'ready'
                    and isinstance(commit, str) and re.fullmatch(r'[0-9a-f]{7,40}', commit)):
                return commit
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        if attempt + 1 < attempts:
            sleep(10)
    raise RuntimeError('healthy_production_backup_source_unavailable')


if __name__ == '__main__':
    print('source_commit=' + wait_for_backup_source(sys.argv[1]))
