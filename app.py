import calendar
import os
import sqlite3
from datetime import date, datetime

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import get_db, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
    insert_expense,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

EXPENSE_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


def _initials(name):
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _parse_date_param(value):
    """Return a date object if value is a well-formed YYYY-MM-DD string,
    else None (covers missing, empty, and malformed values uniformly)."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _shift_months_back(d, months):
    """Return the date `months` calendar months before d, with the
    day-of-month clamped to the target month's actual length (e.g.
    Mar 31 minus 1 month -> Feb 28/29, not a crash or rollover)."""
    total = d.month - 1 - months
    year = d.year + total // 12
    month = total % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _resolve_presets(today):
    """Return dict of preset_id -> (date_from_iso, date_to_iso), each
    a tuple of ISO date strings (or (None, None) for "all time")."""
    return {
        "this_month": (today.replace(day=1).isoformat(), today.isoformat()),
        "last_3_months": (_shift_months_back(today, 3).isoformat(), today.isoformat()),
        "last_6_months": (_shift_months_back(today, 6).isoformat(), today.isoformat()),
        "all_time": (None, None),
    }


def _resolve_date_range(args):
    """Parse date_from/date_to out of request.args, returning a validated
    (date_from_iso, date_to_iso) pair or (None, None) for "no filter".
    Malformed or one-sided input silently falls back to no filter; an
    inverted range (date_from > date_to) also falls back, but flashes an
    error first."""
    parsed_from = _parse_date_param(args.get("date_from"))
    parsed_to = _parse_date_param(args.get("date_to"))

    if not (parsed_from and parsed_to):
        return None, None

    if parsed_from > parsed_to:
        flash("Start date must be before end date.", "error")
        return None, None

    return parsed_from.isoformat(), parsed_to.isoformat()


with app.app_context():
    init_db()
    seed_db()


@app.context_processor
def inject_user():
    return {"current_user_name": session.get("user_name")}


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("landing"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not email or not password or not confirm_password:
        return render_template(
            "register.html", error="All fields are required.", name=name, email=email
        )

    if len(password) < 8:
        return render_template(
            "register.html",
            error="Password must be at least 8 characters.",
            name=name,
            email=email,
        )

    if password != confirm_password:
        return render_template(
            "register.html",
            error="Passwords do not match.",
            name=name,
            email=email,
        )

    password_hash = generate_password_hash(password)

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return render_template(
            "register.html",
            error="An account with this email already exists.",
            name=name,
            email=email,
        )
    finally:
        conn.close()

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    conn = get_db()
    try:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
    finally:
        conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html", error="Invalid email or password.", email=email
        )

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]

    return redirect(url_for("profile"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    date_from, date_to = _resolve_date_range(request.args)

    user = get_user_by_id(user_id)
    user["initials"] = _initials(user["name"])

    stats = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    transactions = get_recent_transactions(user_id, date_from=date_from, date_to=date_to)
    categories = get_category_breakdown(user_id, date_from=date_from, date_to=date_to)

    presets = _resolve_presets(datetime.now().date())
    preset_by_range = {v: k for k, v in presets.items() if k != "all_time"}

    if not request.args:
        active_preset = "all_time"
    else:
        active_preset = preset_by_range.get((date_from, date_to))

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        presets=presets,
        active_preset=active_preset,
        filter_date_from=date_from or "",
        filter_date_to=date_to or "",
    )


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template(
            "add_expense.html",
            categories=EXPENSE_CATEGORIES,
            today=date.today().isoformat(),
        )

    amount_raw = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    date_raw = request.form.get("date", "").strip()
    description_raw = request.form.get("description", "").strip()
    description = description_raw or None

    error = None
    amount = None

    if not amount_raw:
        error = "Amount is required."
    else:
        try:
            amount = float(amount_raw)
            if amount <= 0 or amount > 10_000_000:
                error = "Amount must be between 0 and 10,000,000."
        except ValueError:
            error = "Amount must be a valid number."

    if not error and category not in EXPENSE_CATEGORIES:
        error = "Please select a valid category."

    parsed_date = _parse_date_param(date_raw) if not error else None
    if not error and parsed_date is None:
        error = "Please enter a valid date."
    elif not error and parsed_date > date.today():
        error = "Date cannot be in the future."

    if error:
        return render_template(
            "add_expense.html",
            categories=EXPENSE_CATEGORIES,
            error=error,
            amount=amount_raw,
            category=category,
            date=date_raw,
            description=description_raw,
        )

    insert_expense(session["user_id"], amount, category, parsed_date.isoformat(), description)
    flash("Expense added.", "success")

    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
