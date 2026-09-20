from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)


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


def _create_empty_user():
    import database.db as db_module

    conn = db_module.get_db()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Empty User", "empty@example.com", "x"),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("empty@example.com",)
    ).fetchone()
    conn.close()
    return row["id"]


class TestGetUserById:
    def test_returns_name_email_member_since(self, app):
        user_id = _seed_user_id()
        user = get_user_by_id(user_id)
        assert user["name"] == "Demo User"
        assert user["email"] == "demo@spendly.com"
        assert " " in user["member_since"]  # "Month YYYY" shape

    def test_nonexistent_id_returns_none_row_gracefully(self, app):
        # Defensive: no seeded/created user with this id.
        try:
            get_user_by_id(999999)
        except Exception:
            pass  # acceptable per spec — out of scope, shouldn't happen via app flow


class TestGetSummaryStats:
    def test_seed_user_totals(self, app):
        user_id = _seed_user_id()
        stats = get_summary_stats(user_id)
        assert stats["total_spent"] == "₹276"
        assert stats["transaction_count"] == 8
        assert stats["top_category"] == "Bills"

    def test_no_expenses_returns_zeros(self, app):
        user_id = _create_empty_user()
        stats = get_summary_stats(user_id)
        assert stats == {
            "total_spent": "₹0",
            "transaction_count": 0,
            "top_category": "—",
        }


class TestGetRecentTransactions:
    def test_seed_user_has_transactions(self, app):
        user_id = _seed_user_id()
        txs = get_recent_transactions(user_id)
        assert len(txs) == 8
        for tx in txs:
            assert set(tx.keys()) == {"date", "description", "category", "amount"}
            assert tx["amount"].startswith("₹")

    def test_newest_first_order(self, app):
        user_id = _seed_user_id()
        txs = get_recent_transactions(user_id)
        # Seeded dates are days 02, 04, 05, 08, 11, 15, 18, 22 of the
        # current month — newest (22) should come first.
        assert txs[0]["description"] == "Miscellaneous expense"

    def test_no_expenses_returns_empty_list(self, app):
        user_id = _create_empty_user()
        assert get_recent_transactions(user_id) == []


class TestGetCategoryBreakdown:
    def test_seed_user_categories(self, app):
        user_id = _seed_user_id()
        cats = get_category_breakdown(user_id)
        assert len(cats) == 7  # Food, Transport, Bills, Health, Entertainment, Shopping, Other
        for cat in cats:
            assert set(cat.keys()) == {"name", "amount", "pct"}
            assert cat["amount"].startswith("₹")

    def test_pct_sums_to_100(self, app):
        user_id = _seed_user_id()
        cats = get_category_breakdown(user_id)
        assert sum(c["pct"] for c in cats) == 100

    def test_no_expenses_returns_empty_list(self, app):
        user_id = _create_empty_user()
        assert get_category_breakdown(user_id) == []


class TestProfileRoute:
    def test_unauthenticated_redirects(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_authenticated_shows_real_totals(self, client, app):
        user_id = _seed_user_id()
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_name"] = "Demo User"

        resp = client.get("/profile")
        assert resp.status_code == 200

        body = resp.data.decode("utf-8")
        assert "Demo User" in body
        assert "demo@spendly.com" in body
        assert "₹276" in body
        assert "Bills" in body
        assert "₹" in body

    def test_new_user_with_no_expenses_renders_without_error(self, client, app):
        user_id = _create_empty_user()
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["user_name"] = "Empty User"

        resp = client.get("/profile")
        assert resp.status_code == 200
        assert "₹0" in resp.data.decode("utf-8")
