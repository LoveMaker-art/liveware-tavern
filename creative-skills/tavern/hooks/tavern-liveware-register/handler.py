import subprocess
from pathlib import Path

RUNNER = Path('/opt/data/hooks/tavern-liveware-register/run.sh')
LOG = Path('/opt/data/logs/tavern-liveware-register-hook.log')


def handle(event_type, context):
    if event_type != 'gateway:startup':
        return
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as log:
        log.write('gateway:startup received; spawning tavern liveware ensure\n')
        subprocess.Popen(
            ['/bin/sh', str(RUNNER)],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
