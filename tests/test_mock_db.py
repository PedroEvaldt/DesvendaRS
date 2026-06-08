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
        redflag_fornecedor_repetida = con.execute(
            """
            SELECT COUNT(*)
              FROM (
                    SELECT escopo, cnpj, sinal, COUNT(*) AS n
                      FROM redflag_eventos
                     WHERE escopo = 'fornecedor'
                     GROUP BY escopo, cnpj, sinal
                    HAVING COUNT(*) > 1
                   )
            """
        ).fetchone()[0]
        redflag_licitacao_repetida = con.execute(
            """
            SELECT COUNT(*)
              FROM (
                    SELECT escopo, cd_orgao, nr_licitacao, ano_licitacao,
                           cd_tipo_modalidade, sinal, COUNT(*) AS n
                      FROM redflag_eventos
                     WHERE escopo = 'licitacao'
                     GROUP BY escopo, cd_orgao, nr_licitacao, ano_licitacao,
                              cd_tipo_modalidade, sinal
                    HAVING COUNT(*) > 1
                   )
            """
        ).fetchone()[0]
        redflag_porto_alegre_repetida = con.execute(
            """
            SELECT COUNT(*)
              FROM (
                    SELECT sinal, COUNT(*) AS n
                      FROM redflag_eventos
                     WHERE escopo = 'licitacao'
                       AND cd_orgao = '001'
                       AND nr_licitacao = '100'
                       AND ano_licitacao = '2026'
                       AND cd_tipo_modalidade = 'PRE'
                     GROUP BY sinal
                    HAVING COUNT(*) > 1
                   )
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert contratos == 7
    assert sancoes >= 1
    assert sobrepreco >= 1
    assert cover >= 1
    assert redflag_fornecedor_repetida >= 1
    assert redflag_licitacao_repetida >= 1
    assert redflag_porto_alegre_repetida >= 1
