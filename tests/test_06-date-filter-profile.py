"""Tests for Step 6 — Date Filter for Profile Page.

Spec: .claude/specs/06-date-filter-profile.md

Scope covered:
- GET /profile with no query params behaves identically to Step 5 (unfiltered)
- Each quick-select preset (This Month, Last 3 Months, Last 6 Months, All Time)
- Custom date range (valid, zero-match, boundary-inclusive)
- Auth guard on /profile (still enforced with filter params present)
- Validation: date_from > date_to -> flash + fallback to unfiltered
- Validation: malformed date string -> silent fallback, no crash
- Active-preset / active-range indication in rendered HTML
- Query helper (database/queries.py) date-range filtering correctness,
  independent of the route, including unfiltered-call parity with Step 5

These tests reuse the `app`/`client` fixtures defined in tests/conftest.py,
which wire the Flask app to an isolated temp sqlite DB per test (via
monkeypatching database.db.DB_PATH before import). No source files are
modified; only DB rows are inserted through parameterised SQL for test setup.
"""

import re
from datetime import date, timedelta

import pytest

from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #

def _seed_user_id():
    """The `app` fixture's seed_db() creates 'Demo User' as the first user
    in the fresh temp DB, with 8 sample expenses in the *current* month."""
    import database.db as db_module

    conn = db_module.get_db()
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
    ).fetchone()
    conn.close()
    return row["id"]


def _create_user(email="rangeuser@example.com", name="Range User"):
    import database.db as db_module

    conn = db_module.get_db()
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, "x"),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return row["id"]


def _insert_expense(user_id, amount, category, iso_date, description="test"):
    import database.db as db_module

    conn = db_module.get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, iso_date, description),
    )
    conn.commit()
    conn.close()


def _login(client, user_id, user_name="Test User"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = user_name


def _preset_href(body, link_text):
    """Extract the href of a quick-select preset link by its visible text,
    e.g. _preset_href(body, "This Month") -> "/profile?date_from=...&date_to=...".

    This reads the *rendered HTML* (a spec-mandated landmark: preset links
    must be generated via url_for and reflect computed date bounds), not
    the app's internal implementation.
    """
    match = re.search(
        r'<a href="([^"]+)"[^>]*>' + re.escape(link_text) + r"</a>", body
    )
    assert match, f"Could not find a preset link with text {link_text!r} in rendered page"
    return match.group(1).replace("&amp;", "&")


# --------------------------------------------------------------------- #
# Auth guard — still enforced with filter query params present
# --------------------------------------------------------------------- #

class TestAuthGuard:
    def test_unauthenticated_get_profile_no_params_redirects_to_login(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_unauthenticated_get_profile_with_filter_params_redirects_to_login(
        self, client
    ):
        resp = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")
        assert resp.status_code == 302, "Filter params must not bypass the auth guard"
        assert "/login" in resp.headers["Location"]


# --------------------------------------------------------------------- #
# Route: unfiltered view parity with Step 5
# --------------------------------------------------------------------- #

class TestUnfilteredParity:
    def test_no_query_params_returns_same_totals_as_step5(self, client, app):
        user_id = _seed_user_id()
        _login(client, user_id, "Demo User")

        resp = client.get("/profile")
        assert resp.status_code == 200

        body = resp.data.decode("utf-8")
        assert "₹276" in body, "Unfiltered total must match Step 5 seeded total"
        assert "Bills" in body
        assert "₹" in body

    def test_no_query_params_active_preset_is_all_time(self, client, app):
        user_id = _seed_user_id()
        _login(client, user_id, "Demo User")

        resp = client.get("/profile")
        body = resp.data.decode("utf-8")
        assert "profile-filter-preset-active" in body
        # The "All Time" preset link is a clean /profile URL per spec.
        assert 'href="/profile"' in body


# --------------------------------------------------------------------- #
# Route: quick-select presets
# --------------------------------------------------------------------- #

class TestPresets:
    """These tests read the rendered preset <a href> links (a spec-mandated
    landmark — links must be generated via url_for with computed date
    bounds) and follow them, rather than guessing the date math ourselves.
    This validates the real, wired-up preset behavior end-to-end."""

    def test_this_month_preset_filters_to_current_month(self, client, app):
        user_id = _create_user()
        today = date.today()
        first_of_month = today.replace(day=1)
        last_month_date = first_of_month - timedelta(days=1)

        _insert_expense(user_id, 111.0, "Food", first_of_month.isoformat(), "in this month")
        _insert_expense(user_id, 222.0, "Bills", today.isoformat(), "also this month")
        _insert_expense(user_id, 333.0, "Other", last_month_date.isoformat(), "last month")

        _login(client, user_id)

        # Load the page once (unfiltered) to discover the real preset link.
        landing_body = client.get("/profile").data.decode("utf-8")
        href = _preset_href(landing_body, "This Month")

        resp = client.get(href)
        body = resp.data.decode("utf-8")
        assert resp.status_code == 200
        assert "in this month" in body
        assert "also this month" in body
        assert "last month" not in body
        assert "₹333" not in body

    def test_last_3_months_preset_includes_expenses_in_window(self, client, app):
        user_id = _create_user()
        today = date.today()
        in_window = today - timedelta(days=60)  # ~2 months back
        outside_window = today - timedelta(days=200)  # well beyond 3 months

        _insert_expense(user_id, 50.0, "Food", in_window.isoformat(), "within 3mo")
        _insert_expense(user_id, 77.0, "Other", outside_window.isoformat(), "beyond 3mo")

        _login(client, user_id)

        landing_body = client.get("/profile").data.decode("utf-8")
        href = _preset_href(landing_body, "Last 3 Months")

        resp = client.get(href)
        body = resp.data.decode("utf-8")
        assert resp.status_code == 200
        assert "within 3mo" in body
        assert "beyond 3mo" not in body

    def test_last_6_months_preset_includes_expenses_in_window(self, client, app):
        user_id = _create_user()
        today = date.today()
        in_window = today - timedelta(days=150)  # ~5 months back
        outside_window = today - timedelta(days=400)  # well beyond 6 months

        _insert_expense(user_id, 60.0, "Food", in_window.isoformat(), "within 6mo")
        _insert_expense(user_id, 88.0, "Other", outside_window.isoformat(), "beyond 6mo")

        _login(client, user_id)

        landing_body = client.get("/profile").data.decode("utf-8")
        href = _preset_href(landing_body, "Last 6 Months")

        resp = client.get(href)
        body = resp.data.decode("utf-8")
        assert resp.status_code == 200
        assert "within 6mo" in body
        assert "beyond 6mo" not in body

    def test_all_time_preset_link_is_clean_url_with_no_query_params(self, client, app):
        user_id = _seed_user_id()
        _login(client, user_id, "Demo User")

        # Land on a filtered view first so "All Time" is a genuine escape hatch.
        filtered_body = client.get(
            "/profile?date_from=2020-01-01&date_to=2020-01-02"
        ).data.decode("utf-8")
        href = _preset_href(filtered_body, "All Time")

        # Per spec: "The All Time preset must pass no query params
        # (clean /profile URL)".
        assert href == "/profile", f"Expected clean /profile URL, got {href!r}"

        resp = client.get(href)
        body = resp.data.decode("utf-8")
        assert resp.status_code == 200
        assert "₹276" in body


# --------------------------------------------------------------------- #
# Route: custom date range
# --------------------------------------------------------------------- #

class TestCustomRange:
    def test_custom_range_shows_only_expenses_within_range(self, client, app):
        user_id = _create_user()
        _insert_expense(user_id, 10.0, "Food", "2026-01-05")
        _insert_expense(user_id, 20.0, "Food", "2026-01-15")
        _insert_expense(user_id, 555.0, "Food", "2026-02-01")  # outside range

        _login(client, user_id)

        resp = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "₹30" in body  # total of the two Jan expenses (10+20), distinct from the excluded 555
        assert "₹555" not in body
        assert "2" in body  # transaction count

    def test_custom_range_boundary_dates_are_inclusive(self, client, app):
        user_id = _create_user()
        # Exactly on both boundaries.
        _insert_expense(user_id, 15.0, "Food", "2026-03-01", "start boundary")
        _insert_expense(user_id, 25.0, "Food", "2026-03-31", "end boundary")
        _insert_expense(user_id, 40.0, "Food", "2026-04-01", "just outside")

        _login(client, user_id)

        resp = client.get("/profile?date_from=2026-03-01&date_to=2026-03-31")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "start boundary" in body
        assert "end boundary" in body
        assert "just outside" not in body

    def test_custom_range_zero_matches_shows_zero_state(self, client, app):
        user_id = _create_user()
        _insert_expense(user_id, 99.0, "Food", "2026-05-01")

        _login(client, user_id)

        # Range that deliberately excludes the only expense.
        resp = client.get("/profile?date_from=2026-06-01&date_to=2026-06-30")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "₹0" in body
        assert "0" in body  # transaction_count
        assert "99" not in body

    def test_custom_range_reflected_back_into_filter_inputs(self, client, app):
        user_id = _create_user()
        _login(client, user_id)

        resp = client.get("/profile?date_from=2026-01-01&date_to=2026-01-31")
        body = resp.data.decode("utf-8")
        assert resp.status_code == 200
        assert 'value="2026-01-01"' in body
        assert 'value="2026-01-31"' in body


# --------------------------------------------------------------------- #
# Route: validation — date_from > date_to
# --------------------------------------------------------------------- #

class TestInvalidRangeOrder:
    def test_date_from_after_date_to_flashes_error_and_falls_back(self, client, app):
        user_id = _seed_user_id()
        _login(client, user_id, "Demo User")

        resp = client.get(
            "/profile?date_from=2026-02-01&date_to=2026-01-01", follow_redirects=True
        )
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "Start date must be before end date." in body, (
            "Expected flash message per spec when date_from > date_to"
        )
        # Falls back to unfiltered (Step 5 seeded total).
        assert "₹276" in body

    def test_date_from_after_date_to_does_not_crash(self, client, app):
        user_id = _seed_user_id()
        _login(client, user_id, "Demo User")

        resp = client.get("/profile?date_from=2026-12-31&date_to=2026-01-01")
        assert resp.status_code == 200


# --------------------------------------------------------------------- #
# Route: validation — malformed date strings
# --------------------------------------------------------------------- #

class TestMalformedDates:
    @pytest.mark.parametrize(
        "date_from,date_to",
        [
            ("not-a-date", "2026-01-31"),
            ("2026-01-01", "not-a-date"),
            ("not-a-date", "not-a-date"),
            ("2026/01/01", "2026/01/31"),  # wrong separator
            ("", "2026-01-31"),
            ("2026-13-40", "2026-01-31"),  # invalid month/day values
        ],
    )
    def test_malformed_date_falls_back_silently_without_crashing(
        self, client, app, date_from, date_to
    ):
        user_id = _seed_user_id()
        _login(client, user_id, "Demo User")

        resp = client.get(f"/profile?date_from={date_from}&date_to={date_to}")
        assert resp.status_code == 200, "Malformed date input must not crash the app"
        body = resp.data.decode("utf-8")
        # Falls back to unfiltered view (Step 5 seeded total), no error page.
        assert "₹276" in body

    def test_malformed_date_does_not_trigger_range_order_flash(self, client, app):
        user_id = _seed_user_id()
        _login(client, user_id, "Demo User")

        resp = client.get("/profile?date_from=garbage&date_to=2026-01-31")
        body = resp.data.decode("utf-8")
        # Only a well-formed date_from > date_to should ever produce this
        # flash; a malformed param should be silently treated as absent.
        assert "Start date must be before end date." not in body


# --------------------------------------------------------------------- #
# Route: active-filter visual indication
# --------------------------------------------------------------------- #

class TestActiveFilterIndication:
    def test_custom_range_matching_no_preset_has_no_active_preset_highlighted(
        self, client, app
    ):
        user_id = _seed_user_id()
        _login(client, user_id, "Demo User")

        # An arbitrary custom range unlikely to equal any preset's bounds.
        resp = client.get("/profile?date_from=2020-01-01&date_to=2020-01-02")
        body = resp.data.decode("utf-8")
        assert resp.status_code == 200
        assert "profile-filter-preset-active" not in body, (
            "No quick-select preset should be highlighted for an unrelated custom range"
        )

    def test_all_time_view_highlights_all_time_preset(self, client, app):
        user_id = _seed_user_id()
        _login(client, user_id, "Demo User")

        resp = client.get("/profile")
        body = resp.data.decode("utf-8")
        assert "profile-filter-preset-active" in body


# --------------------------------------------------------------------- #
# Route: ₹ symbol persists regardless of filter state
# --------------------------------------------------------------------- #

class TestCurrencySymbolPersists:
    @pytest.mark.parametrize(
        "query_string",
        [
            "",
            "?date_from=2026-01-01&date_to=2026-01-31",
            "?date_from=bad&date_to=bad",
            "?date_from=2026-02-01&date_to=2026-01-01",  # invalid order
        ],
    )
    def test_rupee_symbol_present_across_filter_states(
        self, client, app, query_string
    ):
        user_id = _seed_user_id()
        _login(client, user_id, "Demo User")

        resp = client.get(f"/profile{query_string}", follow_redirects=True)
        assert resp.status_code == 200
        assert "₹" in resp.data.decode("utf-8")


# --------------------------------------------------------------------- #
# database/queries.py — get_summary_stats date filtering
# --------------------------------------------------------------------- #

class TestGetSummaryStatsDateFilter:
    def test_unfiltered_call_behaves_as_before_step6(self, app):
        user_id = _seed_user_id()
        stats = get_summary_stats(user_id)
        assert stats["total_spent"] == "₹276"
        assert stats["transaction_count"] == 8
        assert stats["top_category"] == "Bills"

    def test_date_range_filters_totals_and_count(self, app):
        user_id = _create_user()
        _insert_expense(user_id, 10.0, "Food", "2026-01-05")
        _insert_expense(user_id, 20.0, "Food", "2026-01-15")
        _insert_expense(user_id, 30.0, "Bills", "2026-02-01")

        stats = get_summary_stats(user_id, date_from="2026-01-01", date_to="2026-01-31")
        assert stats["total_spent"] == "₹30"
        assert stats["transaction_count"] == 2
        assert stats["top_category"] == "Food"

    def test_boundary_dates_are_inclusive(self, app):
        user_id = _create_user()
        _insert_expense(user_id, 5.0, "Food", "2026-03-01")
        _insert_expense(user_id, 7.0, "Food", "2026-03-31")

        stats = get_summary_stats(user_id, date_from="2026-03-01", date_to="2026-03-31")
        assert stats["transaction_count"] == 2
        assert stats["total_spent"] == "₹12"

    def test_zero_match_range_returns_zero_state(self, app):
        user_id = _create_user()
        _insert_expense(user_id, 99.0, "Food", "2026-05-01")

        stats = get_summary_stats(user_id, date_from="2026-06-01", date_to="2026-06-30")
        assert stats == {
            "total_spent": "₹0",
            "transaction_count": 0,
            "top_category": "—",
        }

    def test_one_sided_bound_does_not_raise(self, app):
        # Spec: "when both are provided, add AND date BETWEEN ? AND ?" —
        # implying a single provided bound must not raise an error. The
        # route layer only ever supplies both-or-neither (app.py falls
        # back to None/None otherwise), so we only assert no crash here.
        user_id = _seed_user_id()
        try:
            get_summary_stats(user_id, date_from="2026-01-01", date_to=None)
        except Exception as exc:
            pytest.fail(f"One-sided date bound must not raise, got: {exc!r}")


# --------------------------------------------------------------------- #
# database/queries.py — get_recent_transactions date filtering
# --------------------------------------------------------------------- #

class TestGetRecentTransactionsDateFilter:
    def test_unfiltered_call_behaves_as_before_step6(self, app):
        user_id = _seed_user_id()
        txs = get_recent_transactions(user_id)
        assert len(txs) == 8
        assert txs[0]["description"] == "Miscellaneous expense"

    def test_date_range_filters_and_preserves_order(self, app):
        user_id = _create_user()
        _insert_expense(user_id, 10.0, "Food", "2026-01-05", "early")
        _insert_expense(user_id, 20.0, "Food", "2026-01-15", "mid")
        _insert_expense(user_id, 30.0, "Bills", "2026-02-01", "excluded")

        txs = get_recent_transactions(user_id, date_from="2026-01-01", date_to="2026-01-31")
        assert len(txs) == 2
        # Most recent first within the filtered range.
        assert txs[0]["description"] == "mid"
        assert txs[1]["description"] == "early"
        assert all("excluded" != tx["description"] for tx in txs)

    def test_limit_still_respected_with_date_filter(self, app):
        user_id = _create_user()
        for day in range(1, 6):
            _insert_expense(user_id, 1.0 * day, "Food", f"2026-01-{day:02d}")

        txs = get_recent_transactions(
            user_id, limit=2, date_from="2026-01-01", date_to="2026-01-31"
        )
        assert len(txs) == 2

    def test_zero_match_range_returns_empty_list(self, app):
        user_id = _create_user()
        _insert_expense(user_id, 5.0, "Food", "2026-05-01")

        txs = get_recent_transactions(user_id, date_from="2026-06-01", date_to="2026-06-30")
        assert txs == []


# --------------------------------------------------------------------- #
# database/queries.py — get_category_breakdown date filtering
# --------------------------------------------------------------------- #

class TestGetCategoryBreakdownDateFilter:
    def test_unfiltered_call_behaves_as_before_step6(self, app):
        user_id = _seed_user_id()
        cats = get_category_breakdown(user_id)
        assert len(cats) == 7
        assert sum(c["pct"] for c in cats) == 100

    def test_date_range_filters_categories_and_recalculates_pct(self, app):
        user_id = _create_user()
        _insert_expense(user_id, 10.0, "Food", "2026-01-05")
        _insert_expense(user_id, 30.0, "Bills", "2026-01-15")
        _insert_expense(user_id, 999.0, "Other", "2026-02-01")  # outside range

        cats = get_category_breakdown(user_id, date_from="2026-01-01", date_to="2026-01-31")
        names = {c["name"] for c in cats}
        assert names == {"Food", "Bills"}
        assert "Other" not in names
        assert sum(c["pct"] for c in cats) == 100

    def test_zero_match_range_returns_empty_list(self, app):
        user_id = _create_user()
        _insert_expense(user_id, 5.0, "Food", "2026-05-01")

        cats = get_category_breakdown(user_id, date_from="2026-06-01", date_to="2026-06-30")
        assert cats == []
