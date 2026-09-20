"""Pure DB query helpers for the profile page.

No Flask imports. Each function opens its own connection via get_db()
and closes it before returning. All amount fields are returned as
pre-formatted Indian Rupee strings (e.g. "₹1,200") to match the
existing template convention (profile.html has no Jinja number filters).
"""

from datetime import datetime

from database.db import get_db


def _format_inr(amount):
    """Format a numeric amount as an Indian Rupee string with thousands
    separators, e.g. 1200 -> "₹1,200", 350.5 -> "₹350" (rounded to whole
    rupees, matching the existing hardcoded template style)."""
    return f"₹{round(amount):,}"


def _largest_remainder_pct(totals):
    grand_total = sum(totals)
    if grand_total <= 0:
        return [0 for _ in totals]
    raw = [t / grand_total * 100 for t in totals]
    floored = [int(p) for p in raw]
    remainder = 100 - sum(floored)
    if remainder > 0:
        floored[totals.index(max(totals))] += remainder
    return floored


# --------------------------------------------------------------------- #
# SUBAGENT 3 owns this function. Do not edit outside this block.
# --------------------------------------------------------------------- #
def get_user_by_id(user_id):
    """Return dict with name, email, member_since ("Month YYYY")."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    dt = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": dt.strftime("%B %Y"),
    }
# --------------------------------------------------------------------- #


# --------------------------------------------------------------------- #
# SUBAGENT 2 owns this function. Do not edit outside this block.
# --------------------------------------------------------------------- #
def get_summary_stats(user_id):
    """Return dict with total_spent (₹ string), transaction_count (int),
    top_category (str, "—" if no expenses)."""
    conn = get_db()
    try:
        transaction_count = conn.execute(
            "SELECT COUNT(*) FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]

        if transaction_count == 0:
            return {
                "total_spent": "₹0",
                "transaction_count": 0,
                "top_category": "—",
            }

        total_amount = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]

        top_category_row = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    top_category = top_category_row["category"] if top_category_row else "—"

    return {
        "total_spent": _format_inr(total_amount),
        "transaction_count": transaction_count,
        "top_category": top_category,
    }
# --------------------------------------------------------------------- #


# --------------------------------------------------------------------- #
# SUBAGENT 1 owns this function. Do not edit outside this block.
# --------------------------------------------------------------------- #
def get_recent_transactions(user_id, limit=10):
    """Return list of dicts: date, description, category, amount (₹ string).
    Most recent first. Empty list if no expenses."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()

    transactions = []
    for row in rows:
        dt = datetime.strptime(row["date"], "%Y-%m-%d")
        display_date = dt.strftime("%b") + f" {dt.day}, " + dt.strftime("%Y")
        transactions.append({
            "date": display_date,
            "description": row["description"],
            "category": row["category"],
            "amount": _format_inr(row["amount"]),
        })
    return transactions
# --------------------------------------------------------------------- #


# --------------------------------------------------------------------- #
# SUBAGENT 3 owns this function. Do not edit outside this block.
# --------------------------------------------------------------------- #
def get_category_breakdown(user_id):
    """Return list of dicts: name, amount (₹ string), pct (int, sums to
    100, largest category absorbs rounding remainder). Empty list if no
    expenses."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) as total FROM expenses "
            "WHERE user_id = ? GROUP BY category ORDER BY total DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    totals = [row["total"] for row in rows]
    pcts = _largest_remainder_pct(totals)

    return [
        {
            "name": row["category"],
            "amount": _format_inr(row["total"]),
            "pct": pct,
        }
        for row, pct in zip(rows, pcts)
    ]
# --------------------------------------------------------------------- #
