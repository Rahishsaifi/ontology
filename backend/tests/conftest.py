import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        demo_mode=True,
        graph_backend="memory",
        data_dir=str(tmp_path),
        inline_jobs=True,
        source_system="successfactors",
        app_api_token="reader-token",
        app_admin_token="admin-token",
        sf_page_size=50,
        samples_dir=str(ROOT / "samples"),
    )


@pytest.fixture
def client(settings):
    application = create_app(settings)
    with TestClient(application) as test_client:
        test_client.app_state = application
        yield test_client


def admin():
    return {"Authorization": "Bearer admin-token"}


def reader():
    return {"Authorization": "Bearer reader-token"}


def sample_mappings():
    return json.loads((ROOT / "samples" / "reviewed-mappings.json").read_text(encoding="utf-8"))
