"""Tests for Step 9 — Delete Expense.

Spec: .claude/specs/09-delete-expense.md
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


class TestDeleteExpense:
    def test_deletes_own_expense(self, app):
        from database.queries import delete_expense

        user_id = _create_second_user()
        expense_id = _insert_expense_for(user_id)

        delete_expense(expense_id, user_id)

        assert _fetch_one_expense(expense_id) is None

    def test_does_not_delete_other_users_expense(self, app):
        from database.queries import delete_expense

        owner_id = _create_second_user()
        expense_id = _insert_expense_for(owner_id)

        other_id = _seed_user_id()
        delete_expense(expense_id, other_id)

        row = _fetch_one_expense(expense_id)
        assert row is not None
        assert row["amount"] == 50.0

    def test_nonexistent_expense_is_a_noop(self, app):
        from database.queries import delete_expense

        user_id = _seed_user_id()
        # Should not raise, even though no row matches.
        delete_expense(999999, user_id)


class TestDeleteExpenseRoute:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.post("/expenses/1/delete")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_get_is_not_allowed(self, client):
        user_id = _seed_user_id()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id)

        resp = client.get(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 405

    def test_own_expense_is_deleted_and_redirects(self, client):
        user_id = _seed_user_id()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id)

        resp = client.post(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 302
        assert "/profile" in resp.headers["Location"]

        assert _fetch_one_expense(expense_id) is None

    def test_valid_delete_flashes_success_message(self, client):
        user_id = _seed_user_id()
        expense_id = _insert_expense_for(user_id)
        _login(client, user_id)

        resp = client.post(f"/expenses/{expense_id}/delete", follow_redirects=True)
        assert resp.status_code == 200
        assert "Expense deleted" in resp.get_data(as_text=True)

    def test_other_users_expense_returns_404_and_does_not_delete(self, client):
        owner_id = _create_second_user()
        expense_id = _insert_expense_for(owner_id)

        viewer_id = _seed_user_id()
        _login(client, viewer_id)

        resp = client.post(f"/expenses/{expense_id}/delete")
        assert resp.status_code == 404

        row = _fetch_one_expense(expense_id)
        assert row is not None
        assert row["amount"] == 50.0

    def test_nonexistent_expense_returns_404(self, client):
        user_id = _seed_user_id()
        _login(client, user_id)

        resp = client.post("/expenses/999999/delete")
        assert resp.status_code == 404
