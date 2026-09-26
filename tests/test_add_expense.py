"""Tests for Step 7 — Add Expense.

Spec: .claude/specs/07-add-expense.md
"""


def _seed_user_id():
    # seed_db() (run by the `app` fixture) creates "Demo User" /
    # demo@spendly.com as the first user in the fresh temp DB.
    import database.db as db_module

    conn = db_module.get_db()
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
    ).fetchone()
    conn.close()
    return row["id"]


def _create_second_user():
    import database.db as db_module

    conn = db_module.get_db()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Second User", "second@example.com", "x"),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("second@example.com",)
    ).fetchone()
    conn.close()
    return row["id"]


def _login(client, user_id, user_name="Demo User"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = user_name


def _fetch_expenses(user_id):
    import database.db as db_module

    conn = db_module.get_db()
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC", (user_id,)
    ).fetchall()
    conn.close()
    return rows


class TestInsertExpense:
    def test_valid_row_is_inserted(self, app):
        # seed_db() (run by the `app` fixture) already seeds 8 sample
        # expenses for the demo user, so insert against a fresh user with
        # no pre-existing expenses to keep the assertion unambiguous.
        from database.queries import insert_expense

        user_id = _create_second_user()
        insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")

        rows = _fetch_expenses(user_id)
        assert len(rows) == 1
        assert rows[0]["amount"] == 50.0
        assert rows[0]["category"] == "Food"
        assert rows[0]["date"] == "2026-03-20"
        assert rows[0]["description"] == "Lunch"

    def test_none_description_stored_as_null(self, app):
        from database.queries import insert_expense

        user_id = _create_second_user()
        insert_expense(user_id, 20.0, "Other", "2026-03-21", None)

        rows = _fetch_expenses(user_id)
        assert rows[0]["description"] is None


class TestGetAddExpense:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/expenses/add")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_authenticated_returns_form(self, client):
        user_id = _seed_user_id()
        _login(client, user_id)

        resp = client.get("/expenses/add")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)

        for cat in ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]:
            assert f">{cat}<" in body

        assert "<form" in body
        assert "POST" in body.upper()


class TestPostAddExpense:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.post("/expenses/add", data={
            "amount": "50.0", "category": "Food", "date": "2026-03-20", "description": "Lunch",
        })
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_valid_submission_redirects_and_inserts(self, client):
        user_id = _seed_user_id()
        _login(client, user_id)

        resp = client.post("/expenses/add", data={
            "amount": "50.0", "category": "Food", "date": "2026-03-20", "description": "Lunch",
        })
        assert resp.status_code == 302
        assert "/profile" in resp.headers["Location"]

        rows = _fetch_expenses(user_id)
        assert any(
            r["amount"] == 50.0 and r["category"] == "Food"
            and r["date"] == "2026-03-20" and r["description"] == "Lunch"
            for r in rows
        )

    def test_valid_submission_flashes_success_message(self, client):
        user_id = _seed_user_id()
        _login(client, user_id)

        resp = client.post(
            "/expenses/add",
            data={"amount": "50.0", "category": "Food", "date": "2026-03-20", "description": "Lunch"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Expense added" in resp.get_data(as_text=True)

    def test_missing_amount_reshows_form_with_error(self, client):
        # Use a fresh user with no seeded expenses so "no row inserted" can
        # be asserted as an empty list rather than a before/after count.
        user_id = _create_second_user()
        _login(client, user_id, user_name="Second User")

        resp = client.post("/expenses/add", data={
            "amount": "", "category": "Food", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 200
        assert "required" in resp.get_data(as_text=True).lower()
        assert _fetch_expenses(user_id) == []

    def test_zero_amount_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        _login(client, user_id, user_name="Second User")

        resp = client.post("/expenses/add", data={
            "amount": "0", "category": "Food", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 200
        assert "amount must be between" in resp.get_data(as_text=True).lower()
        assert _fetch_expenses(user_id) == []

    def test_negative_amount_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        _login(client, user_id, user_name="Second User")

        resp = client.post("/expenses/add", data={
            "amount": "-10", "category": "Food", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 200
        assert "amount must be between" in resp.get_data(as_text=True).lower()
        assert _fetch_expenses(user_id) == []

    def test_excessive_amount_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        _login(client, user_id, user_name="Second User")

        resp = client.post("/expenses/add", data={
            "amount": "50000000", "category": "Food", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 200
        assert "amount must be between" in resp.get_data(as_text=True).lower()
        assert _fetch_expenses(user_id) == []

    def test_non_numeric_amount_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        _login(client, user_id, user_name="Second User")

        resp = client.post("/expenses/add", data={
            "amount": "abc", "category": "Food", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 200
        assert "valid number" in resp.get_data(as_text=True).lower()
        assert _fetch_expenses(user_id) == []

    def test_invalid_category_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        _login(client, user_id, user_name="Second User")

        resp = client.post("/expenses/add", data={
            "amount": "50.0", "category": "NotACategory", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 200
        assert "category" in resp.get_data(as_text=True).lower()
        assert _fetch_expenses(user_id) == []

    def test_invalid_date_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        _login(client, user_id, user_name="Second User")

        resp = client.post("/expenses/add", data={
            "amount": "50.0", "category": "Food", "date": "not-a-date", "description": "",
        })
        assert resp.status_code == 200
        assert "date" in resp.get_data(as_text=True).lower()
        assert _fetch_expenses(user_id) == []

    def test_future_date_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        _login(client, user_id, user_name="Second User")

        resp = client.post("/expenses/add", data={
            "amount": "50.0", "category": "Food", "date": "2999-01-01", "description": "",
        })
        assert resp.status_code == 200
        assert "future" in resp.get_data(as_text=True).lower()
        assert _fetch_expenses(user_id) == []

    def test_no_description_saves_with_null(self, client):
        user_id = _seed_user_id()
        _login(client, user_id)

        resp = client.post("/expenses/add", data={
            "amount": "15.0", "category": "Shopping", "date": "2026-03-22", "description": "",
        })
        assert resp.status_code == 302
        assert "/profile" in resp.headers["Location"]

        rows = _fetch_expenses(user_id)
        match = next(r for r in rows if r["amount"] == 15.0 and r["category"] == "Shopping")
        assert match["description"] is None

    def test_expense_attributed_to_logged_in_user_only(self, client):
        user_id = _seed_user_id()
        demo_expense_count_before = len(_fetch_expenses(user_id))
        other_user_id = _create_second_user()
        _login(client, other_user_id, user_name="Second User")

        resp = client.post("/expenses/add", data={
            "amount": "30.0", "category": "Bills", "date": "2026-03-23", "description": "Water bill",
        })
        assert resp.status_code == 302

        assert len(_fetch_expenses(other_user_id)) == 1
        assert len(_fetch_expenses(user_id)) == demo_expense_count_before
