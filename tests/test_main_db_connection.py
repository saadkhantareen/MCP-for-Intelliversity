import pytest
from django.db import connections
from django.db.utils import OperationalError


@pytest.mark.django_db
def test_default_db_connection():
    try:
        connections["default"].ensure_connection()
        assert connections["default"].is_usable()
    except OperationalError as exc:
        pytest.fail(f"Database connection failed: {exc}")
