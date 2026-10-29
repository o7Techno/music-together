from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.core.config import Settings
from tests.live import create_schema, live_server, make_settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    db_path = tmp_path / "test.db"
    asyncio.run(create_schema(db_path))
    return make_settings(db_path)


@pytest.fixture
def server(settings: Settings) -> Iterator[str]:
    with live_server(settings) as base:
        yield base
