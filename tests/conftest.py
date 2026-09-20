import sys

import pytest


@pytest.fixture()
def app(tmp_path, monkeypatch):
    """Provide a Flask app wired to an isolated, temporary sqlite DB.

    Patches database.db.DB_PATH to a per-test temp file BEFORE importing
    app.py, so the module-level init_db()/seed_db() call in app.py never
    touches the real expense_tracker.db.
    """
    db_path = tmp_path / "test_expense_tracker.db"

    # Force a clean import of database.db and app for every test, since
    # app.py runs init_db()/seed_db() as import-time side effects tied to
    # whatever DB_PATH is active at import time.
    for mod_name in ("app", "database.db", "database.queries"):
        sys.modules.pop(mod_name, None)

    import database.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))

    import app as app_module  # triggers init_db()+seed_db() against db_path

    app_module.app.config.update(TESTING=True)

    yield app_module.app

    for mod_name in ("app", "database.db", "database.queries"):
        sys.modules.pop(mod_name, None)


@pytest.fixture()
def client(app):
    return app.test_client()
