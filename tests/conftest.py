from pathlib import Path

import pytest

from backend.app.catalog import load_catalog
from backend.app.config import DEFAULT_DATA_PATH, ROOT


@pytest.fixture(scope="session")
def catalog():
    return load_catalog(ROOT / DEFAULT_DATA_PATH)


@pytest.fixture
def fixture_path():
    return Path(__file__).parent / "fixtures" / "catalog.csv"
