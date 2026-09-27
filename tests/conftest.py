"""
Test configuration guards.

The checked-in ``.env`` mirrors the deployment configuration, which means
``DATABASE_URL`` can point at the live Neon database. Tests must never touch it,
and several test modules call ``create_app()`` without arguments, so the
environment is forced to a throwaway SQLite file *before* the application (and
therefore ``app.config.load_dotenv``) is imported.

``load_dotenv`` does not override variables that are already set, so these values
win over anything in ``.env``.
"""

import os
import pathlib
import tempfile

_TEST_DB = pathlib.Path(tempfile.gettempdir()) / "ki_asset_management_tests.db"
_TEST_DB.unlink(missing_ok=True)

os.environ["FLASK_CONFIG"] = "development"
os.environ["USE_LOCAL_SQLITE"] = "True"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["NEON_OPTIMIZE"] = "false"
os.environ["LOG_LEVEL"] = os.environ.get("TEST_LOG_LEVEL", "WARNING")
os.environ["LOG_HTTP_REQUESTS"] = "false"
# Keep any accidental email path from reaching a real SMTP server.
os.environ["MAIL_SUPPRESS_SEND"] = "True"
