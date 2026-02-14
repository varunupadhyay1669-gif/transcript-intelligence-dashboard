"""
Playwright E2E test — conftest providing a fresh database for each test run.
"""
import pytest
import os
import sys
import subprocess
import time
import signal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

BASE_URL = "http://127.0.0.1:5001"


@pytest.fixture(scope="session")
def base_url():
    """Return the base URL for the running server."""
    return BASE_URL


@pytest.fixture(scope="session")
def reset_db():
    """Reset the database before the test suite and seed fresh data."""
    import requests
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "db", "data.sqlite")

    # Delete existing database
    if os.path.exists(db_path):
        os.remove(db_path)

    # Restart the server by importing and re-initializing
    # The server should already be running; we just need to re-create schema
    from lib.db import get_db, _init_schema
    import lib.db as db_module
    db_module._conn = None  # Force reconnect

    conn = get_db()  # This re-creates schema

    # Seed via API
    resp = requests.post(f"{BASE_URL}/api/seed")
    assert resp.status_code == 201

    return True
