"""Tests for Step 7 — Add Expense.

Spec: .claude/specs/07-add-expense.md

Scope covered (derived from the spec only — not from reading app.py's
route implementation):
- `insert_expense` query helper: valid insert, and description=None stored
  as NULL
- GET /expenses/add — auth guard (redirect to /login when logged out)
- GET /expenses/add — authenticated: 200, form with POST method, category
  <select> containing all 7 fixed categories
- POST /expenses/add — auth guard (redirect to /login when logged out)
- POST /expenses/add — happy path: valid data redirects to /profile and the
  row is persisted for the correct user
- POST /expenses/add — validation errors re-render the form (200) with an
  error message for: missing amount, zero amount, non-numeric amount,
  invalid category, invalid date string
- POST /expenses/add — optional description: omitting it still succeeds
  and the stored value is NULL
- Definition-of-done checks: previously entered values are retained when
  re-rendering after a validation error

These tests reuse the `app`/`client` fixtures defined in tests/conftest.py,
which wire the Flask app to an isolated temp sqlite DB per test (via
monkeypatching database.db.DB_PATH before import). No source files are
modified; only DB rows are inserted/read through parameterised SQL for
test setup and assertions.
"""

import pytest


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #

EXPENSE_CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


def _create_user(email="addexpense@example.com", name="Add Expense User", password="testpass123"):
    """Register a user via the real /register route so password hashing
    and validation match production behaviour, then return the user id."""
    import database.db as db_module

    conn = db_module.get_db()
    row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    if row:
        return row["id"]

    from werkzeug.security import generate_password_hash

    conn = db_module.get_db()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, generate_password_hash(password)),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    return row["id"]


def _login(client, email="addexpense@example.com", password="testpass123"):
    return client.post(
        "/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def _create_and_login(client, email="addexpense@example.com", name="Add Expense User", password="testpass123"):
    user_id = _create_user(email=email, name=name, password=password)
    _login(client, email=email, password=password)
    return user_id


def _fetch_expenses_for_user(user_id):
    import database.db as db_module

    conn = db_module.get_db()
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC", (user_id,)
    ).fetchall()
    conn.close()
    return rows


# --------------------------------------------------------------------- #
# Unit tests: insert_expense
# --------------------------------------------------------------------- #

class TestInsertExpenseUnit:
    def test_insert_expense_valid_data_row_is_persisted(self, app):
        """insert_expense(user_id, amount=50.0, category='Food',
        date='2026-03-20', description='Lunch') should create a row that
        can be queried back with matching values."""
        # Imported lazily, after the `app` fixture has monkeypatched
        # database.db.DB_PATH and re-imported database.queries, so this
        # binds to the isolated temp-DB module rather than the one loaded
        # at collection time (which would point at the real dev DB).
        from database.queries import insert_expense

        with app.app_context():
            user_id = _create_user()

            insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")

            rows = _fetch_expenses_for_user(user_id)
            assert len(rows) == 1, "Expected exactly one expense row to be inserted"
            row = rows[0]
            assert row["user_id"] == user_id
            assert row["amount"] == 50.0
            assert row["category"] == "Food"
            assert row["date"] == "2026-03-20"
            assert row["description"] == "Lunch"

    def test_insert_expense_description_none_stored_as_null(self, app):
        """When description=None is passed, the stored row's description
        column must be NULL, not an empty string or the literal 'None'."""
        from database.queries import insert_expense

        with app.app_context():
            user_id = _create_user()

            insert_expense(user_id, 20.0, "Transport", "2026-03-21", None)

            rows = _fetch_expenses_for_user(user_id)
            assert len(rows) == 1
            assert rows[0]["description"] is None, (
                "Expected description to be stored as NULL when None is passed"
            )


# --------------------------------------------------------------------- #
# Route tests: GET /expenses/add
# --------------------------------------------------------------------- #

class TestGetAddExpense:
    def test_get_add_expense_unauthenticated_redirects_to_login(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302, "Expected a redirect for unauthenticated GET"
        assert "/login" in response.headers["Location"], "Expected redirect target to be /login"

    def test_get_add_expense_authenticated_returns_200(self, client, app):
        with app.app_context():
            _create_and_login(client)

        response = client.get("/expenses/add")
        assert response.status_code == 200, "Expected 200 for authenticated GET"

    def test_get_add_expense_authenticated_contains_post_form(self, client, app):
        with app.app_context():
            _create_and_login(client)

        response = client.get("/expenses/add")
        body = response.data.decode()

        assert "<form" in body, "Expected a <form> element in the response"
        assert 'method="POST"' in body or "method='POST'" in body or "method=\"post\"" in body.lower(), (
            "Expected the form's method to be POST"
        )

    def test_get_add_expense_authenticated_category_select_has_all_options(self, client, app):
        with app.app_context():
            _create_and_login(client)

        response = client.get("/expenses/add")
        body = response.data.decode()

        assert "<select" in body, "Expected a <select> element for category"
        for category in EXPENSE_CATEGORIES:
            assert category in body, f"Expected category option '{category}' to appear in the form"


# --------------------------------------------------------------------- #
# Route tests: POST /expenses/add — auth guard
# --------------------------------------------------------------------- #

class TestPostAddExpenseAuthGuard:
    def test_post_add_expense_unauthenticated_redirects_to_login(self, client):
        response = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert response.status_code == 302, "Expected a redirect for unauthenticated POST"
        assert "/login" in response.headers["Location"], "Expected redirect target to be /login"

    def test_post_add_expense_unauthenticated_does_not_write_to_db(self, client, app):
        """An unauthenticated POST must not create any expense row at all.

        seed_db() always seeds 8 sample expenses into a fresh DB, so the
        row count is compared before/after rather than asserted to be 0.
        """
        with app.app_context():
            import database.db as db_module

            conn = db_module.get_db()
            count_before = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
            conn.close()

        response = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )
        assert response.status_code == 302

        with app.app_context():
            import database.db as db_module

            conn = db_module.get_db()
            count_after = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
            conn.close()
            assert count_after == count_before, (
                "No expense should be inserted for an unauthenticated request"
            )


# --------------------------------------------------------------------- #
# Route tests: POST /expenses/add — happy path
# --------------------------------------------------------------------- #

class TestPostAddExpenseHappyPath:
    def test_post_valid_data_redirects_to_profile(self, client, app):
        with app.app_context():
            _create_and_login(client)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302, "Expected a redirect on successful submission"
        assert "/profile" in response.headers["Location"], "Expected redirect target to be /profile"

    def test_post_valid_data_creates_row_for_correct_user(self, client, app):
        with app.app_context():
            user_id = _create_and_login(client)

        client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        with app.app_context():
            rows = _fetch_expenses_for_user(user_id)

        matching = [r for r in rows if r["amount"] == 50.0 and r["category"] == "Food"]
        assert len(matching) == 1, "Expected the new expense to exist in the DB for the test user"
        assert matching[0]["date"] == "2026-03-20"
        assert matching[0]["description"] == "Lunch"

    def test_post_valid_data_no_description_redirects_to_profile(self, client, app):
        with app.app_context():
            _create_and_login(client)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "15.25",
                "category": "Bills",
                "date": "2026-04-01",
                "description": "",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302, "Expected a redirect when description is omitted"
        assert "/profile" in response.headers["Location"]

    def test_post_valid_data_no_description_stores_null(self, client, app):
        with app.app_context():
            user_id = _create_and_login(client)

        client.post(
            "/expenses/add",
            data={
                "amount": "15.25",
                "category": "Bills",
                "date": "2026-04-01",
                "description": "",
            },
        )

        with app.app_context():
            rows = _fetch_expenses_for_user(user_id)

        matching = [r for r in rows if r["amount"] == 15.25 and r["category"] == "Bills"]
        assert len(matching) == 1, "Expected the expense row to be created"
        assert matching[0]["description"] is None, (
            "Expected description to be NULL when omitted from the form"
        )


# --------------------------------------------------------------------- #
# Route tests: POST /expenses/add — validation errors
# --------------------------------------------------------------------- #

class TestPostAddExpenseValidation:
    def test_post_missing_amount_rerenders_form_with_error(self, client, app):
        with app.app_context():
            _create_and_login(client)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        assert response.status_code == 200, "Expected the form to be re-rendered (200), not redirected"
        body = response.data.decode()
        assert "<form" in body, "Expected the add-expense form to be re-rendered"

    def test_post_missing_amount_does_not_create_row(self, client, app):
        with app.app_context():
            user_id = _create_and_login(client)

        client.post(
            "/expenses/add",
            data={
                "amount": "",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        with app.app_context():
            rows = _fetch_expenses_for_user(user_id)
        assert len(rows) == 0, "No row should be inserted when amount is missing"

    def test_post_zero_amount_rerenders_form_with_error(self, client, app):
        with app.app_context():
            _create_and_login(client)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        assert response.status_code == 200, "Zero amount must re-render the form, not succeed"
        body = response.data.decode()
        assert "<form" in body

    def test_post_zero_amount_does_not_create_row(self, client, app):
        with app.app_context():
            user_id = _create_and_login(client)

        client.post(
            "/expenses/add",
            data={
                "amount": "0",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        with app.app_context():
            rows = _fetch_expenses_for_user(user_id)
        assert len(rows) == 0, "No row should be inserted when amount is 0"

    def test_post_non_numeric_amount_rerenders_form_with_error(self, client, app):
        with app.app_context():
            _create_and_login(client)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "not-a-number",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        assert response.status_code == 200, "Non-numeric amount must re-render the form, not succeed"
        body = response.data.decode()
        assert "<form" in body

    def test_post_non_numeric_amount_does_not_create_row(self, client, app):
        with app.app_context():
            user_id = _create_and_login(client)

        client.post(
            "/expenses/add",
            data={
                "amount": "not-a-number",
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        with app.app_context():
            rows = _fetch_expenses_for_user(user_id)
        assert len(rows) == 0, "No row should be inserted when amount is non-numeric"

    def test_post_invalid_category_rerenders_form_with_error(self, client, app):
        with app.app_context():
            _create_and_login(client)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "NotARealCategory",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        assert response.status_code == 200, "Invalid category must re-render the form, not succeed"
        body = response.data.decode()
        assert "<form" in body

    def test_post_invalid_category_does_not_create_row(self, client, app):
        with app.app_context():
            user_id = _create_and_login(client)

        client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "NotARealCategory",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        with app.app_context():
            rows = _fetch_expenses_for_user(user_id)
        assert len(rows) == 0, "No row should be inserted when category is invalid"

    def test_post_invalid_date_rerenders_form_with_error(self, client, app):
        with app.app_context():
            _create_and_login(client)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "not-a-date",
                "description": "Lunch",
            },
        )

        assert response.status_code == 200, "Invalid date must re-render the form, not succeed"
        body = response.data.decode()
        assert "<form" in body

    def test_post_invalid_date_does_not_create_row(self, client, app):
        with app.app_context():
            user_id = _create_and_login(client)

        client.post(
            "/expenses/add",
            data={
                "amount": "50.0",
                "category": "Food",
                "date": "not-a-date",
                "description": "Lunch",
            },
        )

        with app.app_context():
            rows = _fetch_expenses_for_user(user_id)
        assert len(rows) == 0, "No row should be inserted when date is invalid"

    @pytest.mark.parametrize(
        "bad_amount",
        ["", "0", "-5", "abc", "0.00"],
    )
    def test_post_various_invalid_amounts_never_create_a_row(self, client, app, bad_amount):
        """Data-driven sweep over amount values that must all be rejected:
        missing, zero, negative, non-numeric, and zero-as-decimal."""
        with app.app_context():
            user_id = _create_and_login(client, email=f"user{hash(bad_amount) & 0xffff}@example.com")

        response = client.post(
            "/expenses/add",
            data={
                "amount": bad_amount,
                "category": "Food",
                "date": "2026-03-20",
                "description": "Lunch",
            },
        )

        assert response.status_code == 200, f"Amount {bad_amount!r} should be rejected and re-render the form"

        with app.app_context():
            rows = _fetch_expenses_for_user(user_id)
        assert len(rows) == 0, f"No row should be inserted for invalid amount {bad_amount!r}"


# --------------------------------------------------------------------- #
# Definition of done: previously entered values retained on error
# --------------------------------------------------------------------- #

class TestFormRepopulationOnError:
    def test_invalid_category_retains_previously_entered_amount_and_date(self, client, app):
        """Per spec: 'On any validation error, re-render the form with the
        error message and the previously submitted values pre-filled.'"""
        with app.app_context():
            _create_and_login(client)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "73.50",
                "category": "InvalidCategory",
                "date": "2026-05-15",
                "description": "Weekend trip",
            },
        )

        assert response.status_code == 200
        body = response.data.decode()
        assert "73.50" in body, "Expected previously entered amount to be retained in the re-rendered form"
        assert "2026-05-15" in body, "Expected previously entered date to be retained in the re-rendered form"
        assert "Weekend trip" in body, "Expected previously entered description to be retained in the re-rendered form"

    def test_missing_amount_retains_previously_entered_category_and_description(self, client, app):
        with app.app_context():
            _create_and_login(client)

        response = client.post(
            "/expenses/add",
            data={
                "amount": "",
                "category": "Health",
                "date": "2026-05-16",
                "description": "Doctor visit",
            },
        )

        assert response.status_code == 200
        body = response.data.decode()
        assert "Doctor visit" in body, "Expected previously entered description to be retained"
        assert "2026-05-16" in body, "Expected previously entered date to be retained"
