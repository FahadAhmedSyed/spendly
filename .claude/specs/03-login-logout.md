# Spec: Login and Logout

## Overview
This feature implements authentication for Spendly: a working POST handler for the
existing `/login` route, session-based login state using Flask's built-in signed
cookie session, and a real `/logout` route that clears that session. It replaces the
placeholder `/logout` route and turns the login form (currently GET-only, POST target
with no handler) into a functional sign-in flow. This is the step that makes
"logged-in" a real concept in the app, which later steps (profile, expenses) depend on.

## Depends on
- Step 1 — Database Setup (`users` table, `get_db`)
- Step 2 — Registration (users can already create accounts with hashed passwords)

## Routes
- `POST /login` — authenticate a user by email + password, start a session — public
- `GET /login` — render the login form (already exists, unchanged) — public
- `GET /logout` — clear the session and redirect to landing — logged-in

## Database changes
No database changes. The existing `users` table (`id`, `name`, `email`,
`password_hash`, `created_at`) is sufficient — verified against `database/db.py`.

## Templates
- **Create:** none
- **Modify:** `templates/login.html` — no structural changes needed; it already POSTs
  to `/login` and renders an `error` variable the same way `register.html` does

## Files to change
- `app.py` — add `SECRET_KEY` config for session signing, implement POST handling on
  `/login` (validate credentials with `check_password_hash`, set `session["user_id"]`
  and `session["user_name"]` on success), implement `/logout` to `session.clear()` and
  redirect to `landing`

## Files to create
None.

## New dependencies
No new dependencies. Flask's built-in `session` and
`werkzeug.security.check_password_hash` are already available.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (`check_password_hash` against `password_hash`)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Look up the user by email, then verify the password with `check_password_hash`;
  never compare plaintext passwords
- On failed login, re-render `login.html` with a generic error (do not reveal
  whether the email exists or the password was wrong)
- Store only `user_id` (and optionally `user_name` for display) in the session —
  never store the password or password hash
- `app.secret_key` must be set for sessions to work; a hardcoded dev value is
  acceptable at this stage, consistent with `debug=True` in `app.py`

## Definition of done
- [ ] Visiting `/login` still renders the sign-in form
- [ ] Submitting `/login` with the seeded demo account (`demo@spendly.com` /
      `demo123`) redirects successfully and does not show an error
- [ ] Submitting `/login` with a wrong password re-renders `login.html` with an
      error message and no redirect
- [ ] Submitting `/login` with an email that doesn't exist re-renders `login.html`
      with the same generic error message as a wrong password
- [ ] After a successful login, visiting `/logout` clears the session and redirects
      to the landing page (`/`)
- [ ] After `/logout`, the session no longer contains `user_id`
