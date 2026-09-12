# Step 1 — Database Setup

import os
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "expense_tracker.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing > 0:
        conn.close()
        return

    password_hash = generate_password_hash("demo123")
    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", password_hash),
    )
    user_id = cursor.lastrowid

    today = datetime.now()
    year, month = today.year, today.month

    sample_expenses = [
        (user_id, 12.50, "Food", f"{year:04d}-{month:02d}-02", "Lunch at cafe"),
        (user_id, 45.00, "Transport", f"{year:04d}-{month:02d}-04", "Monthly bus pass"),
        (user_id, 89.99, "Bills", f"{year:04d}-{month:02d}-05", "Electricity bill"),
        (user_id, 25.00, "Health", f"{year:04d}-{month:02d}-08", "Pharmacy purchase"),
        (user_id, 15.00, "Entertainment", f"{year:04d}-{month:02d}-11", "Movie ticket"),
        (user_id, 60.00, "Shopping", f"{year:04d}-{month:02d}-15", "New shoes"),
        (user_id, 8.75, "Food", f"{year:04d}-{month:02d}-18", "Groceries"),
        (user_id, 20.00, "Other", f"{year:04d}-{month:02d}-22", "Miscellaneous expense"),
    ]

    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        sample_expenses,
    )
    conn.commit()
    conn.close()
