"""Test session setup.

Forcing ENVIRONMENT=test here (before any app import triggers get_settings)
makes the process-global engine use NullPool — required for the sync TestClient,
whose per-request event loops can't share pooled connections. Environment
variables take precedence over .env in pydantic-settings, so this wins.
"""

import os

os.environ["ENVIRONMENT"] = "test"

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()
