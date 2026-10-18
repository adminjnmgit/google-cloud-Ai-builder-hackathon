"""WSGI entry point for Cloud Run and ``flask --app wsgi ...``."""

from __future__ import annotations

import os

from werkzeug.middleware.proxy_fix import ProxyFix

from orbit import create_app
from orbit.database import migrate_to_head

app = create_app()
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

if os.environ.get('ORBIT_MIGRATE_ON_START', '').strip().lower() in {'1', 'true', 'yes', 'on'}:
    with app.app_context():
        migrate_to_head()
