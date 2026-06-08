"""Tests for the local mock database generator."""
from __future__ import annotations

import duckdb

from scripts.create_mock_db import main


def test_create_mock_db(tmp_path, monkeypatch):
    db_path = tmp_path / "mock.duckdb"
    monkeypatch.setattr("sys.argv", ["create_mock_db.py", "--path", str(db_path)])

    main()

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        contratos = con.execute("SELECT COUNT(*) FROM contratos").fetchone()[0]
        sancoes = con.execute("SELECT COUNT(*) FROM vw_contratos_com_sancao").fetchone()[0]
        sobrepreco = con.execute("SELECT COUNT(*) FROM vw_sobrepreco_indicios").fetchone()[0]
        cover = con.execute("SELECT COUNT(*) FROM vw_cover_bidding_indicios").fetchone()[0]
    finally:
        con.close()

    assert contratos == 6
    assert sancoes >= 1
    assert sobrepreco >= 1
    assert cover >= 1
