"""Tests for Step 8 — Edit Expense.

Spec: .claude/specs/08-edit-expense.md
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


def _fetch_one_expense(expense_id):
    import database.db as db_module

    conn = db_module.get_db()
    row = conn.execute(
        "SELECT * FROM expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    conn.close()
    return row


def _insert_expense_for(user_id, amount=50.0, category="Food", date="2026-03-20", description="Lunch"):
    from database.queries import insert_expense

    insert_expense(user_id, amount, category, date, description)
    return _fetch_expenses(user_id)[0]["id"]


class TestGetExpenseById:
    def test_returns_dict_for_own_expense(self, app):
        from database.queries import get_expense_by_id

        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id)

        result = get_expense_by_id(expense_id, user_id)
        assert result == {
            "id": expense_id,
            "amount": 50.0,
            "category": "Food",
            "date": "2026-03-20",
            "description": "Lunch",
        }

    def test_returns_none_for_other_users_expense(self, app):
        from database.queries import get_expense_by_id

        owner_id = _create_second_user()
        expense_id = _insert_expense_for(owner_id)

        other_id = _seed_user_id()
        assert get_expense_by_id(expense_id, other_id) is None

    def test_returns_none_for_nonexistent_id(self, app):
        from database.queries import get_expense_by_id

        user_id = _seed_user_id()
        assert get_expense_by_id(999999, user_id) is None


class TestUpdateExpense:
    def test_updates_own_expense_fields(self, app):
        from database.queries import update_expense

        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id)

        update_expense(expense_id, user_id, 99.0, "Bills", "2026-04-01", "Updated")

        row = _fetch_one_expense(expense_id)
        assert row["amount"] == 99.0
        assert row["category"] == "Bills"
        assert row["date"] == "2026-04-01"
        assert row["description"] == "Updated"

    def test_does_not_update_other_users_expense(self, app):
        from database.queries import update_expense

        owner_id = _create_second_user()
        expense_id = _insert_expense_for(owner_id)

        other_id = _seed_user_id()
        update_expense(expense_id, other_id, 99.0, "Bills", "2026-04-01", "Updated")

        row = _fetch_one_expense(expense_id)
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_none_description_stored_as_null(self, app):
        from database.queries import update_expense

        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id)

        update_expense(expense_id, user_id, 99.0, "Bills", "2026-04-01", None)

        row = _fetch_one_expense(expense_id)
        assert row["description"] is None


class TestGetEditExpense:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/expenses/1/edit")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_own_expense_returns_prefilled_form(self, client):
        user_id = _seed_user_id()
        expense_id = _insert_expense_for(user_id, amount=75.5, category="Bills", date="2026-03-15", description="Water bill")
        _login(client, user_id)

        resp = client.get(f"/expenses/{expense_id}/edit")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)

        assert "Water bill" in body
        assert '<option value="Bills" selected>Bills</option>' in body
        assert "<form" in body
        assert "POST" in body.upper()

    def test_other_users_expense_returns_404(self, client):
        owner_id = _create_second_user()
        expense_id = _insert_expense_for(owner_id)

        viewer_id = _seed_user_id()
        _login(client, viewer_id)

        resp = client.get(f"/expenses/{expense_id}/edit")
        assert resp.status_code == 404

    def test_nonexistent_expense_returns_404(self, client):
        user_id = _seed_user_id()
        _login(client, user_id)

        resp = client.get("/expenses/999999/edit")
        assert resp.status_code == 404


class TestPostEditExpense:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.post("/expenses/1/edit", data={
            "amount": "50.0", "category": "Food", "date": "2026-03-20", "description": "Lunch",
        })
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_valid_submission_redirects_and_updates(self, client):
        user_id = _seed_user_id()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id)

        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "99.0", "category": "Bills", "date": "2026-04-01", "description": "Updated",
        })
        assert resp.status_code == 302
        assert "/profile" in resp.headers["Location"]

        row = _fetch_one_expense(expense_id)
        assert row["amount"] == 99.0
        assert row["category"] == "Bills"
        assert row["date"] == "2026-04-01"
        assert row["description"] == "Updated"

    def test_valid_submission_flashes_success_message(self, client):
        user_id = _seed_user_id()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id)

        resp = client.post(
            f"/expenses/{expense_id}/edit",
            data={"amount": "99.0", "category": "Bills", "date": "2026-04-01", "description": "Updated"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "Expense updated" in resp.get_data(as_text=True)

    def test_other_users_expense_returns_404_and_does_not_update(self, client):
        owner_id = _create_second_user()
        expense_id = _insert_expense_for(owner_id)

        viewer_id = _seed_user_id()
        _login(client, viewer_id)

        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "99.0", "category": "Bills", "date": "2026-04-01", "description": "Updated",
        })
        assert resp.status_code == 404

        row = _fetch_one_expense(expense_id)
        assert row["amount"] == 50.0
        assert row["category"] == "Food"

    def test_nonexistent_expense_returns_404(self, client):
        user_id = _seed_user_id()
        _login(client, user_id)

        resp = client.post("/expenses/999999/edit", data={
            "amount": "99.0", "category": "Bills", "date": "2026-04-01", "description": "Updated",
        })
        assert resp.status_code == 404

    def test_missing_amount_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id, user_name="Second User")

        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "", "category": "Food", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 200
        assert "required" in resp.get_data(as_text=True).lower()

        row = _fetch_one_expense(expense_id)
        assert row["amount"] == 50.0

    def test_zero_amount_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id, user_name="Second User")

        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "0", "category": "Food", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 200
        assert "amount must be between" in resp.get_data(as_text=True).lower()
        assert _fetch_one_expense(expense_id)["amount"] == 50.0

    def test_negative_amount_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id, user_name="Second User")

        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "-10", "category": "Food", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 200
        assert "amount must be between" in resp.get_data(as_text=True).lower()
        assert _fetch_one_expense(expense_id)["amount"] == 50.0

    def test_excessive_amount_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id, user_name="Second User")

        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50000000", "category": "Food", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 200
        assert "amount must be between" in resp.get_data(as_text=True).lower()
        assert _fetch_one_expense(expense_id)["amount"] == 50.0

    def test_non_numeric_amount_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id, user_name="Second User")

        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "abc", "category": "Food", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 200
        assert "valid number" in resp.get_data(as_text=True).lower()
        assert _fetch_one_expense(expense_id)["amount"] == 50.0

    def test_invalid_category_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id, user_name="Second User")

        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.0", "category": "NotACategory", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 200
        assert "category" in resp.get_data(as_text=True).lower()
        assert _fetch_one_expense(expense_id)["category"] == "Food"

    def test_invalid_date_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id, user_name="Second User")

        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.0", "category": "Food", "date": "not-a-date", "description": "",
        })
        assert resp.status_code == 200
        assert "date" in resp.get_data(as_text=True).lower()
        assert _fetch_one_expense(expense_id)["date"] == "2026-03-20"

    def test_future_date_reshows_form_with_error(self, client):
        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id, user_name="Second User")

        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.0", "category": "Food", "date": "2999-01-01", "description": "",
        })
        assert resp.status_code == 200
        assert "future" in resp.get_data(as_text=True).lower()
        assert _fetch_one_expense(expense_id)["date"] == "2026-03-20"

    def test_no_description_update_saves_with_null(self, client):
        user_id = _seed_user_id()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id)

        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "50.0", "category": "Food", "date": "2026-03-20", "description": "",
        })
        assert resp.status_code == 302
        assert "/profile" in resp.headers["Location"]

        assert _fetch_one_expense(expense_id)["description"] is None

    def test_error_rerender_shows_submitted_values_not_original(self, client):
        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id, amount=100.0, category="Food", date="2026-03-20", description="Original")
        _login(client, user_id, user_name="Second User")

        resp = client.post(f"/expenses/{expense_id}/edit", data={
            "amount": "", "category": "Bills", "date": "2026-04-05", "description": "Changed",
        })
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)

        assert '<option value="Bills" selected>Bills</option>' in body
        assert "Changed" in body
        assert '<option value="Food" selected>Food</option>' not in body
        assert "Original" not in body

        row = _fetch_one_expense(expense_id)
        assert row["amount"] == 100.0
        assert row["category"] == "Food"
