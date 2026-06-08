"""Orquestra o pipeline: lê CSVs de data/raw/ e (re)cria db/dados.duckdb do zero.

Saída: `db/dados.duckdb` com 8 tabelas (`contratos`, `empresas`, `socios`,
`sancoes`, `itens`, `propostas`, `propostas_itens`, `eventos_licitacao`) e
7 views (sanção, sobrepreço, cover bidding, proposta única, alteração de
edital). Depois calcula red flags e scores em tabelas próprias. Ao final,
imprime um relatório de qualidade com contagens, % de nulos nas colunas-chave,
tamanho dos JOINs entre tabelas e alertas com score alto.
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
from etl.load_eventos import load_eventos
from etl.load_itens import load_itens
from etl.load_propostas import load_propostas
from etl.load_propostas_itens import load_propostas_itens
from etl.load_sancoes import load_sancoes
from etl.load_socios import load_socios
from etl.score_redflags import criar_tabelas_score

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
            CAST(flag_covid AS BOOLEAN)        AS flag_covid,
            CAST(cd_orgao AS VARCHAR)          AS cd_orgao,
            CAST(nr_licitacao AS VARCHAR)      AS nr_licitacao,
            CAST(ano_licitacao AS VARCHAR)     AS ano_licitacao,
            CAST(cd_tipo_modalidade AS VARCHAR) AS cd_tipo_modalidade,
            CAST(cnpj_vencedor AS VARCHAR)     AS cnpj_vencedor
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
    "itens": """
        CREATE TABLE itens AS
        SELECT
            CAST(cd_orgao AS VARCHAR)              AS cd_orgao,
            CAST(nr_licitacao AS VARCHAR)          AS nr_licitacao,
            CAST(ano_licitacao AS VARCHAR)         AS ano_licitacao,
            CAST(cd_tipo_modalidade AS VARCHAR)    AS cd_tipo_modalidade,
            CAST(nr_lote AS VARCHAR)               AS nr_lote,
            CAST(nr_item AS VARCHAR)               AS nr_item,
            CAST(cnpj_fornecedor AS VARCHAR)       AS cnpj_fornecedor,
            CAST(descricao AS VARCHAR)             AS descricao,
            CAST(descricao_normalizada AS VARCHAR) AS descricao_normalizada,
            CAST(quantidade AS DECIMAL(18,4))      AS quantidade,
            CAST(unidade AS VARCHAR)               AS unidade,
            CAST(valor_unitario_estimado AS DECIMAL(18,4))   AS valor_unitario_estimado,
            CAST(valor_unitario_homologado AS DECIMAL(18,4)) AS valor_unitario_homologado,
            CAST(valor_total_homologado AS DECIMAL(18,2))    AS valor_total_homologado,
            CAST(flag_covid AS BOOLEAN)            AS flag_covid
        FROM df
    """,
    "propostas": """
        CREATE TABLE propostas AS
        SELECT
            CAST(cd_orgao AS VARCHAR)              AS cd_orgao,
            CAST(nr_licitacao AS VARCHAR)          AS nr_licitacao,
            CAST(ano_licitacao AS VARCHAR)         AS ano_licitacao,
            CAST(cd_tipo_modalidade AS VARCHAR)    AS cd_tipo_modalidade,
            CAST(cnpj_proposta AS VARCHAR)         AS cnpj_proposta,
            CAST(data_proposta AS DATE)            AS data_proposta,
            CAST(resultado_proposta AS VARCHAR)    AS resultado_proposta,
            CAST(valor_total_proposta AS DECIMAL(18,2))  AS valor_total_proposta,
            CAST(percentual_desconto AS DECIMAL(8,4))    AS percentual_desconto,
            CAST(valor_nota_tecnica AS DECIMAL(18,4))    AS valor_nota_tecnica,
            CAST(data_homologacao AS DATE)         AS data_homologacao
        FROM df
    """,
    "propostas_itens": """
        CREATE TABLE propostas_itens AS
        SELECT
            CAST(cd_orgao AS VARCHAR)              AS cd_orgao,
            CAST(nr_licitacao AS VARCHAR)          AS nr_licitacao,
            CAST(ano_licitacao AS VARCHAR)         AS ano_licitacao,
            CAST(cd_tipo_modalidade AS VARCHAR)    AS cd_tipo_modalidade,
            CAST(nr_lote AS VARCHAR)               AS nr_lote,
            CAST(nr_item AS VARCHAR)               AS nr_item,
            CAST(cnpj_proposta AS VARCHAR)         AS cnpj_proposta,
            CAST(valor_unitario AS DECIMAL(18,4))  AS valor_unitario,
            CAST(valor_total_item AS DECIMAL(18,2)) AS valor_total_item,
            CAST(percentual_desconto AS DECIMAL(8,4)) AS percentual_desconto,
            CAST(percentual_bdi AS DECIMAL(8,4))   AS percentual_bdi,
            CAST(valor_nota_tecnica AS DECIMAL(18,4)) AS valor_nota_tecnica,
            CAST(data_homologacao AS DATE)         AS data_homologacao,
            CAST(resultado_proposta AS VARCHAR)    AS resultado_proposta,
            CAST(resultado_habilitacao AS VARCHAR) AS resultado_habilitacao
        FROM df
    """,
    "eventos_licitacao": """
        CREATE TABLE eventos_licitacao AS
        SELECT
            CAST(cd_orgao AS VARCHAR)              AS cd_orgao,
            CAST(nr_licitacao AS VARCHAR)          AS nr_licitacao,
            CAST(ano_licitacao AS VARCHAR)         AS ano_licitacao,
            CAST(cd_tipo_modalidade AS VARCHAR)    AS cd_tipo_modalidade,
            CAST(sq_evento AS VARCHAR)             AS sq_evento,
            CAST(cd_tipo_fase AS VARCHAR)          AS cd_tipo_fase,
            CAST(cd_tipo_evento AS VARCHAR)        AS cd_tipo_evento,
            CAST(data_evento AS DATE)              AS data_evento,
            CAST(tipo_veiculo_publicacao AS VARCHAR) AS tipo_veiculo_publicacao,
            CAST(descricao_publicacao AS VARCHAR)  AS descricao_publicacao,
            CAST(cnpj_autor AS VARCHAR)            AS cnpj_autor,
            CAST(data_julgamento AS DATE)          AS data_julgamento,
            CAST(tipo_resultado AS VARCHAR)        AS tipo_resultado,
            CAST(nr_lote AS VARCHAR)               AS nr_lote,
            CAST(nr_item AS VARCHAR)               AS nr_item
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
    # Indícios de sobrepreço: agrupa itens por (descricao_normalizada, unidade),
    # calcula mediana do valor unitário homologado, exige massa mínima de 10
    # observações e devolve itens com razão >= 3 vs. mediana do grupo.
    # Limiares (>=3, n>=10) são chute inicial — calibrar após revisão humana.
    "vw_sobrepreco_indicios": """
        CREATE VIEW vw_sobrepreco_indicios AS
        WITH grupo AS (
            SELECT descricao_normalizada, unidade,
                   MEDIAN(valor_unitario_homologado) AS mediana,
                   COUNT(*) AS n_obs
              FROM itens
             WHERE descricao_normalizada IS NOT NULL
               AND valor_unitario_homologado IS NOT NULL
               AND valor_unitario_homologado > 0
               AND unidade IS NOT NULL
             GROUP BY descricao_normalizada, unidade
            HAVING COUNT(*) >= 10
        )
        SELECT i.cd_orgao, i.nr_licitacao, i.ano_licitacao,
               i.cd_tipo_modalidade, i.nr_lote, i.nr_item,
               i.cnpj_fornecedor, i.descricao, i.unidade,
               i.flag_covid,
               i.valor_unitario_homologado,
               g.mediana,
               g.n_obs,
               i.valor_unitario_homologado / g.mediana AS razao_vs_mediana
          FROM itens i
          JOIN grupo g USING (descricao_normalizada, unidade)
         WHERE i.valor_unitario_homologado / g.mediana >= 3
    """,
    # Proposta única classificada: licitação com 1 só proposta sobrevivendo à
    # classificação. Mais forte que qtd_participantes=1 porque desconsidera
    # desclassificadas (proposta apresentada mas inválida).
    "vw_proposta_unica": """
        CREATE VIEW vw_proposta_unica AS
        SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               COUNT(*) AS qtd_propostas_classificadas
          FROM propostas
         WHERE resultado_proposta = 'C'
         GROUP BY cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade
        HAVING COUNT(*) = 1
    """,
    # Indícios de cover bidding: em licitações com >=3 propostas classificadas,
    # razão entre a 2ª menor e a menor. Razão >= 2x = candidato a "proposta
    # perdedora artificialmente alta" (a vencedora "merece" ganhar).
    # Limiar (razão>=2, n>=3) é chute inicial.
    "vw_cover_bidding_indicios": """
        CREATE VIEW vw_cover_bidding_indicios AS
        WITH classificadas AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   cnpj_proposta, valor_total_proposta,
                   ROW_NUMBER() OVER (
                       PARTITION BY cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade
                       ORDER BY valor_total_proposta ASC
                   ) AS rank_preco,
                   COUNT(*) OVER (
                       PARTITION BY cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade
                   ) AS n_classificadas
              FROM propostas
             WHERE resultado_proposta = 'C'
               AND valor_total_proposta IS NOT NULL
               AND valor_total_proposta > 0
        ),
        menor AS (SELECT * FROM classificadas WHERE rank_preco = 1),
        segunda AS (SELECT * FROM classificadas WHERE rank_preco = 2)
        SELECT m.cd_orgao, m.nr_licitacao, m.ano_licitacao, m.cd_tipo_modalidade,
               m.n_classificadas,
               m.cnpj_proposta AS cnpj_vencedora,
               m.valor_total_proposta AS valor_vencedora,
               s.cnpj_proposta AS cnpj_segunda,
               s.valor_total_proposta AS valor_segunda,
               s.valor_total_proposta / m.valor_total_proposta AS razao_2a_vs_1a
          FROM menor m
          JOIN segunda s USING (cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade)
         WHERE m.n_classificadas >= 3
           AND s.valor_total_proposta / m.valor_total_proposta >= 2
    """,
    # Alteração de edital após abertura: eventos do tipo AED (alteração) ou
    # REE (republicação) com data posterior à data de abertura (DT_ABERTURA
    # da licitação na tabela contratos não está preservada; usamos o primeiro
    # PUE — publicação edital — como proxy de abertura formal).
    "vw_alteracao_apos_abertura": """
        CREATE VIEW vw_alteracao_apos_abertura AS
        WITH primeira_pub AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   MIN(data_evento) AS data_publicacao
              FROM eventos_licitacao
             WHERE cd_tipo_evento IN ('PUE', 'PUB')
               AND data_evento IS NOT NULL
             GROUP BY cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade
        )
        SELECT e.cd_orgao, e.nr_licitacao, e.ano_licitacao, e.cd_tipo_modalidade,
               e.cd_tipo_evento,
               p.data_publicacao,
               e.data_evento AS data_alteracao,
               e.data_evento - p.data_publicacao AS dias_apos_publicacao
          FROM eventos_licitacao e
          JOIN primeira_pub p USING (cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade)
         WHERE e.cd_tipo_evento IN ('AED', 'REE')
           AND e.data_evento IS NOT NULL
           AND e.data_evento > p.data_publicacao
    """,
}


def _criar_tabela(con: duckdb.DuckDBPyConnection, nome: str, df: pd.DataFrame) -> None:
    log.info("Gravando tabela %s (%s linhas)", nome, f"{len(df):,}".replace(",", "."))
    con.register("df", df)
    con.execute(f"DROP TABLE IF EXISTS {nome}")
    con.execute(SCHEMAS[nome])
    con.unregister("df")
    # Índice em CNPJ (ou na chave de agrupamento, conforme a tabela)
    if nome == "contratos":
        con.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{nome}_cnpj ON {nome} (cnpj_fornecedor)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_contratos_licitacao "
            "ON contratos (cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade)"
        )
    elif nome == "itens":
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_itens_descricao "
            "ON itens (descricao_normalizada, unidade)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_itens_cnpj ON itens (cnpj_fornecedor)"
        )
    elif nome == "propostas":
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_propostas_cnpj ON propostas (cnpj_proposta)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_propostas_licitacao "
            "ON propostas (cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade)"
        )
    elif nome == "propostas_itens":
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_propostas_itens_cnpj "
            "ON propostas_itens (cnpj_proposta)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_propostas_itens_licitacao "
            "ON propostas_itens (cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade)"
        )
    elif nome == "eventos_licitacao":
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_eventos_licitacao "
            "ON eventos_licitacao (cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_eventos_tipo "
            "ON eventos_licitacao (cd_tipo_evento)"
        )
    else:
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_{nome}_cnpj ON {nome} (cnpj)")


def _relatorio_qualidade(con: duckdb.DuckDBPyConnection) -> None:
    print()
    print("=" * 70)
    print("RELATÓRIO DE QUALIDADE — db/dados.duckdb")
    print("=" * 70)
    chave_por_tabela = {
        "contratos": "cnpj_fornecedor",
        "empresas": "cnpj",
        "socios": "cnpj",
        "sancoes": "cnpj",
        "itens": "cnpj_fornecedor",
        "propostas": "cnpj_proposta",
        "propostas_itens": "cnpj_proposta",
        "eventos_licitacao": "cnpj_autor",
    }
    for tabela, chave in chave_por_tabela.items():
        total = con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]
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
            f"  {tabela:17s} total={total:>10,}  cnpj_distintos={distintos:>9,}  "
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

    print()
    print("Sobrepreço (Fase 2):")
    grupos_total = con.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM itens "
        "WHERE descricao_normalizada IS NOT NULL "
        "AND valor_unitario_homologado IS NOT NULL "
        "AND unidade IS NOT NULL "
        "GROUP BY descricao_normalizada, unidade)"
    ).fetchone()[0]
    grupos_com_massa = con.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM itens "
        "WHERE descricao_normalizada IS NOT NULL "
        "AND valor_unitario_homologado IS NOT NULL "
        "AND unidade IS NOT NULL "
        "GROUP BY descricao_normalizada, unidade HAVING COUNT(*) >= 10)"
    ).fetchone()[0]
    indicios = con.execute("SELECT COUNT(*) FROM vw_sobrepreco_indicios").fetchone()[0]
    print(f"  grupos (descricao×unidade) totais:        {grupos_total:>9,}".replace(",", "."))
    print(f"  grupos com massa estatística (n>=10):     {grupos_com_massa:>9,}".replace(",", "."))
    print(f"  itens marcados como indício de sobrepreço: {indicios:>9,}".replace(",", "."))

    print()
    print("Propostas (Fase 3):")
    p_unica = con.execute("SELECT COUNT(*) FROM vw_proposta_unica").fetchone()[0]
    p_cover = con.execute("SELECT COUNT(*) FROM vw_cover_bidding_indicios").fetchone()[0]
    p_alt = con.execute("SELECT COUNT(*) FROM vw_alteracao_apos_abertura").fetchone()[0]
    print(f"  licitações com proposta única classificada: {p_unica:>9,}".replace(",", "."))
    print(f"  indícios de cover bidding (razão>=2x):       {p_cover:>9,}".replace(",", "."))
    print(f"  eventos de alteração após abertura:          {p_alt:>9,}".replace(",", "."))

    print()
    print("Scores de red flags:")
    total_eventos = con.execute("SELECT COUNT(*) FROM redflag_eventos").fetchone()[0]
    possiveis = con.execute("SELECT COUNT(*) FROM vw_possivel_fraude").fetchone()[0]
    print(f"  eventos de red flag gravados:                {total_eventos:>9,}".replace(",", "."))
    print(f"  entidades com score_bruto >= 100:            {possiveis:>9,}".replace(",", "."))
    top_scores = con.execute(
        """
        SELECT escopo, entidade_id, score_bruto, score, qtd_sinais
          FROM vw_possivel_fraude
         ORDER BY score_bruto DESC, qtd_sinais DESC
         LIMIT 5
        """
    ).fetchall()
    for escopo, entidade_id, score_bruto, score, qtd_sinais in top_scores:
        print(
            "    "
            f"{escopo:10s} score_bruto={score_bruto:>4} score={score:>3} "
            f"sinais={qtd_sinais:>2} entidade={entidade_id}"
        )
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
    itens = load_itens()
    propostas = load_propostas()
    propostas_itens = load_propostas_itens()
    eventos = load_eventos()

    log.info("Conectando ao DuckDB em %s", config.DB_PATH)
    con = duckdb.connect(str(config.DB_PATH))
    try:
        _criar_tabela(con, "contratos", contratos)
        _criar_tabela(con, "empresas", empresas)
        _criar_tabela(con, "socios", socios)
        _criar_tabela(con, "sancoes", sancoes)
        _criar_tabela(con, "itens", itens)
        _criar_tabela(con, "propostas", propostas)
        _criar_tabela(con, "propostas_itens", propostas_itens)
        _criar_tabela(con, "eventos_licitacao", eventos)
        for nome, sql in VIEWS.items():
            log.info("Criando view %s", nome)
            con.execute(f"DROP VIEW IF EXISTS {nome}")
            con.execute(sql)
        criar_tabelas_score(con)
        _relatorio_qualidade(con)
    finally:
        con.close()

    decorrido = time.time() - inicio
    log.info("Pipeline completo em %.1fs", decorrido)


if __name__ == "__main__":
    main()
