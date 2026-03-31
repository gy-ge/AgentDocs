import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_DIR = Path(tempfile.mkdtemp(prefix="agentdocs-tests-"))
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["SQLITE_PATH"] = str(TEST_DIR / "test.db")
os.environ["API_KEY"] = "test-key"

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-key"}