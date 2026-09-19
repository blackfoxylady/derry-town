#!/usr/bin/env python3
"""Create local secrets/configuration, without overwriting existing configuration."""
import argparse
import os
import re
import secrets
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--host', default='localhost', help='Domain or server IPv4, without scheme/port')
p.add_argument('--bind', default='127.0.0.1', choices=['127.0.0.1', '0.0.0.0'])
p.add_argument('--port', type=int, default=8080)
a = p.parse_args()
if not re.fullmatch(r'[a-zA-Z0-9.-]+', a.host) or not 1 <= a.port <= 65535:
    p.error('Invalid host or port.')
target = Path(__file__).resolve().parents[1] / '.env'
content = f'''DJANGO_SECRET_KEY={secrets.token_hex(48)}
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,{a.host}
POSTGRES_DB=derry
POSTGRES_USER=derry
POSTGRES_PASSWORD={secrets.token_hex(32)}
DERRY_BIND={a.bind}
DERRY_PORT={a.port}
DJANGO_TRUST_PROXY=0
DJANGO_SSL_REDIRECT=0
'''
try:
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(content)
except FileExistsError:
    p.exit(1, '.env already exists; preserved. Edit configuration if necessary.\n')
print('Created .env. Secrets are not printed.')
