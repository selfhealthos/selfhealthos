"""Fixtures shared across the test suite.

They live here rather than being imported from one test module into another:
pytest injects fixtures by name, so an import exists only to satisfy the
reader, and ruff correctly reports every test that takes one as redefining it.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()
PASSWORD = "x" * 8  # AUTH_PASSWORD_VALIDATORS is empty; any string is a valid password


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alex", password=PASSWORD, birth_date="1990-01-01")


@pytest.fixture
def client_for():
    def _make(user):
        client = Client()
        client.force_login(user)
        return client

    return _make
