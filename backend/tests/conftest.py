from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture(scope="session")
def client():
    """One FastAPI lifespan for all API/WebSocket tests."""
    with TestClient(app) as test_client:
        yield test_client
