"""Database module — singleton SQLite connection with auto-schema init."""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "data.sqlite")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "schema.sql")

_conn = None


def get_db():
    """Return a singleton database connection, initializing schema if needed."""
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _init_schema(_conn)
    return _conn


def _init_schema(conn):
    """Run schema.sql to create tables if they don't exist."""
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    conn.commit()


def query(sql, params=(), one=False):
    """Execute a SELECT query and return results as list of dicts."""
    conn = get_db()
    cur = conn.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    return rows[0] if one and rows else (None if one else rows)


def execute(sql, params=()):
    """Execute an INSERT/UPDATE/DELETE and return lastrowid."""
    conn = get_db()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid


def executemany(sql, param_list):
    """Execute a statement for multiple parameter sets."""
    conn = get_db()
    conn.executemany(sql, param_list)
    conn.commit()
