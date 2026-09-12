# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

"Spendly" — a Flask-based personal expense tracker built incrementally as a step-by-step course project (CampusX). `app.py` and `database/db.py` contain comments marking work as belonging to specific steps (e.g. "Step 1 — Database Setup", "coming in Step 3"). When asked to implement a feature, check whether it's one of these placeholder steps and follow the existing route/naming conventions rather than redesigning the structure.

## Commands

```bash
source venv/bin/activate       # activate the existing virtualenv (Python 3.11)
pip install -r requirements.txt
python app.py                  # run the dev server on http://localhost:5001 (debug=True)
pytest                         # run tests (pytest + pytest-flask are installed; no tests exist yet)
pytest path/to/test_file.py::test_name   # run a single test
```

There is no build step, linter, or frontend tooling — this is server-rendered Flask with plain CSS/JS.

## Architecture

- **`app.py`** — single Flask app with all routes. Working routes render templates (`/`, `/register`, `/login`, `/terms`, `/privacy`); several routes are intentional placeholders returning plain strings (`/logout`, `/profile`, `/expenses/add`, `/expenses/<id>/edit`, `/expenses/<id>/delete`) awaiting future steps. `/login` and `/register` templates POST to their routes but no POST handler exists yet — auth is unimplemented.
- **`database/db.py`** — currently just a stub comment describing the intended interface: `get_db()` (SQLite connection, row_factory + foreign keys), `init_db()` (CREATE TABLE IF NOT EXISTS), `seed_db()` (sample data). Not yet implemented; the app currently runs with no persistence layer.
- **Templates (`templates/`)** — Jinja2, all extend `base.html` except `landing.html` (standalone). `base.html` defines the shared nav/footer shell and blocks: `title`, `head`, `content`, `scripts`. Use `url_for(<endpoint>)` for internal links, never hardcoded paths.
- **Static assets** — `static/css/style.css` is the shared/base stylesheet (nav, footer, auth forms, etc.) used by everything extending `base.html`. `static/css/landing.css` holds landing-page-only styles (hero, modal) since `landing.html` doesn't extend `base.html`. `static/js/main.js` is an empty shared JS file for future features; page-specific JS (e.g. the landing page's "how it works" video modal) currently lives inline in a `<script>` block in that template rather than in `main.js`.
- No JS framework or bundler is used anywhere — vanilla JS only, by design.
