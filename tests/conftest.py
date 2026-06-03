"""Fixtures compartilhadas pelos testes de integração contra db/dados.duckdb."""
from __future__ import annotations

import duckdb
import pytest

import config


@pytest.fixture(scope="session")
def con() -> duckdb.DuckDBPyConnection:
    """Conexão read-only ao banco gerado por etl/build_db.py."""
    if not config.DB_PATH.exists():
        pytest.skip(
            f"Banco {config.DB_PATH} não existe. Rode `uv run python -m etl.build_db`."
        )
    conexao = duckdb.connect(str(config.DB_PATH), read_only=True)
    try:
        yield conexao
    finally:
        conexao.close()
