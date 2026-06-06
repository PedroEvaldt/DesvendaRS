"""Small DuckDB access layer for the Streamlit app."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

import config


@dataclass(frozen=True)
class DatabaseStatus:
    """Current availability of the generated analytical database."""

    path: Path
    exists: bool
    tables: set[str]
    views: set[str]

    @property
    def ready(self) -> bool:
        required = {"contratos", "empresas", "socios", "sancoes"}
        return self.exists and required.issubset(self.tables)


def connect(db_path: Path = config.DB_PATH, *, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection."""
    return duckdb.connect(str(db_path), read_only=read_only)


def inspect_database(db_path: Path = config.DB_PATH) -> DatabaseStatus:
    """Return database availability and known tables/views without raising for missing DB."""
    if not db_path.exists():
        return DatabaseStatus(path=db_path, exists=False, tables=set(), views=set())

    con = connect(db_path)
    try:
        relations = con.execute(
            """
            SELECT table_name, table_type
              FROM information_schema.tables
             WHERE table_schema = 'main'
            """
        ).fetchall()
    finally:
        con.close()

    tables = {name for name, kind in relations if kind == "BASE TABLE"}
    views = {name for name, kind in relations if kind == "VIEW"}
    return DatabaseStatus(path=db_path, exists=True, tables=tables, views=views)


def query_df(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[Any] | tuple[Any, ...] | None = None,
) -> pd.DataFrame:
    """Execute SQL and return a DataFrame."""
    return con.execute(sql, params or []).fetchdf()


def relation_exists(status: DatabaseStatus, name: str) -> bool:
    """True when a table or view is present in the generated DB."""
    return name in status.tables or name in status.views
