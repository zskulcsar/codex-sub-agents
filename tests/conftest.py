"""Shared pytest fixtures for codex_sub_agent tests."""

import shutil
from pathlib import Path
from typing import Generator

import pytest


@pytest.fixture(scope="session")
def sample_config_dir(tmp_path_factory: pytest.TempPathFactory) -> Generator[Path, None, None]:
    """Return a temporary copy of the repository configuration bundle."""

    temp_dir = tmp_path_factory.mktemp("config_bundle")
    project_root = Path(__file__).resolve().parent.parent
    package_root = project_root / "config"

    dest = temp_dir / "config"
    shutil.copytree(package_root, dest)

    yield dest
