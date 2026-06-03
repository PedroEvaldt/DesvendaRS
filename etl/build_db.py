"""Orquestra o pipeline: lê CSVs de data/raw/ e (re)cria db/dados.duckdb do zero.

Saída: `db/dados.duckdb` com as 4 tabelas (`contratos`, `empresas`, `socios`,
`sancoes`) e algumas views de cruzamento de CNPJ. Ao final, imprime um relatório
de qualidade com contagens, % de nulos nas colunas-chave e tamanho dos JOINs entre
tabelas.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import duckdb
import pandas as pd

import config
from etl.load_contratos import load_contratos
from etl.load_empresas import load_empresas
from etl.load_sancoes import load_sancoes
from etl.load_socios import load_socios

log = logging.getLogger(__name__)


SCHEMAS = {
    "contratos": """
        CREATE TABLE contratos AS
        SELECT
            CAST(cnpj_fornecedor AS VARCHAR)   AS cnpj_fornecedor,
            CAST(razao_social AS VARCHAR)      AS razao_social,
            CAST(orgao AS VARCHAR)             AS orgao,
            CAST(municipio AS VARCHAR)         AS municipio,
            CAST(modalidade AS VARCHAR)        AS modalidade,
            CAST(objeto AS VARCHAR)            AS objeto,
            CAST(valor_contrato AS DECIMAL(18,2)) AS valor_contrato,
            CAST(data_contrato AS DATE)        AS data_contrato,
            CAST(numero_contrato AS VARCHAR)   AS numero_contrato,
            CAST(qtd_participantes AS INTEGER) AS qtd_participantes,
            CAST(flag_covid AS BOOLEAN)        AS flag_covid
        FROM df
    """,
    "empresas": """
        CREATE TABLE empresas AS
        SELECT
            CAST(cnpj AS VARCHAR)             AS cnpj,
            CAST(razao_social AS VARCHAR)     AS razao_social,
            CAST(data_abertura AS DATE)       AS data_abertura,
            CAST(cnae AS VARCHAR)             AS cnae,
            CAST(capital_social AS DECIMAL(18,2)) AS capital_social,
            CAST(situacao_cadastral AS VARCHAR) AS situacao_cadastral,
            CAST(porte AS VARCHAR)            AS porte,
            CAST(endereco AS VARCHAR)         AS endereco,
            CAST(municipio AS VARCHAR)        AS municipio
        FROM df
    """,
    "socios": """
        CREATE TABLE socios AS
        SELECT
            CAST(cnpj AS VARCHAR)         AS cnpj,
            CAST(nome_socio AS VARCHAR)   AS nome_socio,
            CAST(doc_socio AS VARCHAR)    AS doc_socio,
            CAST(tipo_socio AS VARCHAR)   AS tipo_socio,
            CAST(qualificacao AS VARCHAR) AS qualificacao,
            CAST(data_entrada AS DATE)    AS data_entrada
        FROM df
    """,
    "sancoes": """
        CREATE TABLE sancoes AS
        SELECT
            CAST(cnpj AS VARCHAR)              AS cnpj,
            CAST(tipo_sancao AS VARCHAR)       AS tipo_sancao,
            CAST(orgao_sancionador AS VARCHAR) AS orgao_sancionador,
            CAST(data_inicio AS DATE)          AS data_inicio,
            CAST(data_fim AS DATE)             AS data_fim,
            CAST(fonte AS VARCHAR)             AS fonte
        FROM df
    """,
}

VIEWS = {
    "vw_contratos_homologados": """
        CREATE VIEW vw_contratos_homologados AS
        SELECT *
          FROM contratos
         WHERE cnpj_fornecedor IS NOT NULL
           AND valor_contrato IS NOT NULL
           AND data_contrato IS NOT NULL
    """,
    "vw_contratos_com_sancao": """
        CREATE VIEW vw_contratos_com_sancao AS
        SELECT c.*, s.tipo_sancao, s.orgao_sancionador, s.fonte AS fonte_sancao,
               s.data_inicio AS data_inicio_sancao, s.data_fim AS data_fim_sancao
          FROM contratos c
          JOIN sancoes s ON c.cnpj_fornecedor = s.cnpj
    """,
    "vw_empresas_sancionadas": """
        CREATE VIEW vw_empresas_sancionadas AS
        SELECT e.cnpj, e.razao_social, e.data_abertura, e.cnae, e.capital_social,
               s.tipo_sancao, s.fonte, s.data_inicio
          FROM empresas e
          JOIN sancoes s ON e.cnpj = s.cnpj
    """,
}


def _criar_tabela(con: duckdb.DuckDBPyConnection, nome: str, df: pd.DataFrame) -> None:
    log.info("Gravando tabela %s (%s linhas)", nome, f"{len(df):,}".replace(",", "."))
    con.register("df", df)
    con.execute(f"DROP TABLE IF EXISTS {nome}")
    con.execute(SCHEMAS[nome])
    con.unregister("df")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_{nome}_cnpj ON {nome} ("
                + ("cnpj_fornecedor" if nome == "contratos" else "cnpj") + ")")


def _relatorio_qualidade(con: duckdb.DuckDBPyConnection) -> None:
    print()
    print("=" * 70)
    print("RELATÓRIO DE QUALIDADE — db/dados.duckdb")
    print("=" * 70)
    for tabela in ("contratos", "empresas", "socios", "sancoes"):
        total = con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
        chave = "cnpj_fornecedor" if tabela == "contratos" else "cnpj"
        distintos = con.execute(
            f"SELECT COUNT(DISTINCT {chave}) FROM {tabela}"
        ).fetchone()[0]
        nulos = con.execute(
            f"SELECT COUNT(*) FROM {tabela} WHERE {chave} IS NULL"
        ).fetchone()[0]
        invalidos = con.execute(
            f"SELECT COUNT(*) FROM {tabela} "
            f"WHERE {chave} IS NOT NULL AND LENGTH({chave}) <> 14"
        ).fetchone()[0]
        print(
            f"  {tabela:10s}  total={total:>10,}  cnpj_distintos={distintos:>9,}  "
            f"nulos_chave={nulos:>7,}  cnpj_invalido={invalidos:>5,}".replace(",", ".")
        )

    print()
    print("Cruzamentos (cardinalidade dos JOINs por CNPJ):")
    pares = [
        ("contratos ↔ empresas",
         "SELECT COUNT(DISTINCT c.cnpj_fornecedor) "
         "FROM contratos c JOIN empresas e ON c.cnpj_fornecedor = e.cnpj"),
        ("contratos ↔ sancoes",
         "SELECT COUNT(DISTINCT c.cnpj_fornecedor) "
         "FROM contratos c JOIN sancoes s ON c.cnpj_fornecedor = s.cnpj"),
        ("contratos ↔ socios",
         "SELECT COUNT(DISTINCT c.cnpj_fornecedor) "
         "FROM contratos c JOIN socios so ON c.cnpj_fornecedor = so.cnpj"),
        ("empresas ↔ sancoes",
         "SELECT COUNT(DISTINCT e.cnpj) "
         "FROM empresas e JOIN sancoes s ON e.cnpj = s.cnpj"),
        ("empresas ↔ socios",
         "SELECT COUNT(DISTINCT e.cnpj) "
         "FROM empresas e JOIN socios so ON e.cnpj = so.cnpj"),
    ]
    for nome, sql in pares:
        n = con.execute(sql).fetchone()[0]
        print(f"  {nome:25s}  CNPJs em comum: {n:>9,}".replace(",", "."))
    print("=" * 70)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s",
                        datefmt="%H:%M:%S")
    inicio = time.time()

    config.DB_DIR.mkdir(parents=True, exist_ok=True)
    if config.DB_PATH.exists():
        log.info("Removendo banco antigo %s", config.DB_PATH)
        config.DB_PATH.unlink()

    log.info("Carregando dados das fontes")
    contratos = load_contratos()
    empresas = load_empresas()
    socios = load_socios()
    sancoes = load_sancoes()

    log.info("Conectando ao DuckDB em %s", config.DB_PATH)
    con = duckdb.connect(str(config.DB_PATH))
    try:
        _criar_tabela(con, "contratos", contratos)
        _criar_tabela(con, "empresas", empresas)
        _criar_tabela(con, "socios", socios)
        _criar_tabela(con, "sancoes", sancoes)
        for nome, sql in VIEWS.items():
            log.info("Criando view %s", nome)
            con.execute(f"DROP VIEW IF EXISTS {nome}")
            con.execute(sql)
        _relatorio_qualidade(con)
    finally:
        con.close()

    decorrido = time.time() - inicio
    log.info("Pipeline completo em %.1fs", decorrido)


if __name__ == "__main__":
    main()
