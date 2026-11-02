"""Cache only thread-safe repository metadata, never a mutable connection."""
from pathlib import Path
import streamlit as st
from config import Settings
from repository import Repository


@st.cache_resource(show_spinner=False, validate=lambda repo: repo.settings.db_path.is_file())
def get_repository(runtime_path: str, database_path: str) -> Repository:
    repo = Repository(Settings(Path(runtime_path), Path(database_path)))
    repo.initialize()
    return repo


def database_token(repo: Repository) -> tuple:
    paths = [repo.settings.db_path, Path(str(repo.settings.db_path) + '-wal')]
    return tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else (0, 0) for p in paths)


@st.cache_data(ttl=3, show_spinner=False)
def cached_products(database_path: str, token: tuple, _repo: Repository) -> list[dict]:
    return _repo.products()
