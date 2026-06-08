"""Queries SQL reutilizadas pelo site DesvendaRS (independentes de framework).

O banco não preserva a chave composta em algumas análises antigas, então parte das
queries de fila de risco mistura sinais por contrato e por fornecedor. Os rótulos na
interface devem sempre descrever isso como indícios para revisão humana.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import duckdb
import pandas as pd

from app.db import DatabaseStatus, query_df, relation_exists


SCORE_VIEW = "vw_score_contratos"


@dataclass(frozen=True)
class ContractFilters:
    municipio: str | None = None
    orgao: str | None = None
    busca: str | None = None
    minimo_valor: float | None = None
    apenas_covid: bool = False


def has_score_view(status: DatabaseStatus) -> bool:
    """Pessoa 2 can provide this later; the app auto-detects it."""
    return relation_exists(status, SCORE_VIEW)


def overview(con: duckdb.DuckDBPyConnection, status: DatabaseStatus) -> dict[str, Any]:
    """Top-level metrics for the dashboard."""
    base_relation = _contracts_base(status)
    metrics = query_df(
        con,
        f"""
        SELECT
            COUNT(*) AS contratos,
            COALESCE(SUM(valor_contrato), 0) AS valor_total,
            COUNT(DISTINCT cnpj_fornecedor) AS fornecedores,
            COUNT(DISTINCT municipio) AS municipios
          FROM {base_relation}
        """,
    ).iloc[0].to_dict()

    metrics["fornecedores_sancionados"] = 0
    if relation_exists(status, "vw_contratos_com_sancao"):
        metrics["fornecedores_sancionados"] = query_df(
            con,
            """
            SELECT COUNT(DISTINCT cnpj_fornecedor) AS n
              FROM vw_contratos_com_sancao
            """,
        ).iloc[0]["n"]
    return metrics


CHAVE_LICITACAO = ["cd_orgao", "nr_licitacao", "ano_licitacao", "cd_tipo_modalidade"]
ORDENS_LICITACAO = {
    "score": "score DESC NULLS LAST, l.valor_contrato DESC NULLS LAST",
    "data": "l.data_contrato DESC NULLS LAST, score DESC NULLS LAST",
    "valor": "l.valor_contrato DESC NULLS LAST, score DESC NULLS LAST",
    "participantes": "l.qtd_participantes DESC NULLS LAST, score DESC NULLS LAST",
}


def has_score_tables(status: DatabaseStatus) -> bool:
    """True quando o pipeline de red flags (etl/score_redflags) já rodou."""
    return relation_exists(status, "scores_fornecedor")


def has_licitacao_scores(status: DatabaseStatus) -> bool:
    """True quando há scores calculados por chave composta de licitação."""
    return relation_exists(status, "scores_licitacao")


def top_empresas_risco(
    con: duckdb.DuckDBPyConnection,
    status: DatabaseStatus,
    *,
    limit: int = 50,
    busca: str | None = None,
) -> pd.DataFrame:
    """Ranking de empresas por quantidade de red flags e score (home do site).

    Sai de `scores_fornecedor`; razão social vem de `empresas` (fallback `contratos`).
    Ordena por mais sinais e maior score bruto. Devolve DataFrame vazio se o pipeline
    de score ainda não rodou.
    """
    if not has_score_tables(status):
        return pd.DataFrame()
    params: list[Any] = []
    where = ""
    if busca:
        termo = f"%{busca.strip()}%"
        where = "WHERE (nome.razao_social ILIKE ? OR sf.cnpj ILIKE ?)"
        params.extend([termo, termo])
    params.append(limit)
    return query_df(
        con,
        f"""
        WITH nomes AS (
            SELECT cnpj, ANY_VALUE(razao_social) AS razao_social
              FROM empresas GROUP BY cnpj
        ),
        nomes_contrato AS (
            SELECT cnpj_fornecedor AS cnpj, ANY_VALUE(razao_social) AS razao_social
              FROM contratos WHERE cnpj_fornecedor IS NOT NULL GROUP BY cnpj_fornecedor
        )
        SELECT sf.cnpj,
               COALESCE(nome.razao_social, nc.razao_social) AS razao_social,
               sf.score, sf.score_bruto, sf.qtd_sinais, sf.sinais
          FROM scores_fornecedor sf
          LEFT JOIN nomes nome ON nome.cnpj = sf.cnpj
          LEFT JOIN nomes_contrato nc ON nc.cnpj = sf.cnpj
          {where}
         ORDER BY sf.qtd_sinais DESC, sf.score_bruto DESC
         LIMIT ?
        """,
        params,
    )


def empresa_dossie(
    con: duckdb.DuckDBPyConnection,
    status: DatabaseStatus,
    cnpj: str,
) -> dict[str, Any]:
    """Dossiê de uma empresa: score, sinais com evidência, cadastro, sanções e contratos."""
    empresa = query_df(con, "SELECT * FROM empresas WHERE cnpj = ? LIMIT 1", [cnpj])

    score = pd.DataFrame()
    eventos = pd.DataFrame()
    if has_score_tables(status):
        score = query_df(
            con, "SELECT * FROM scores_fornecedor WHERE cnpj = ? LIMIT 1", [cnpj]
        )
        eventos = query_df(
            con,
            """
            SELECT sinal, forca, pontos, evidencia
              FROM redflag_eventos
             WHERE escopo = 'fornecedor' AND cnpj = ?
             ORDER BY pontos DESC
            """,
            [cnpj],
        )
        if not eventos.empty:
            from etl.score_redflags import RED_FLAGS

            eventos["descricao"] = eventos["sinal"].map(
                lambda s: str(RED_FLAGS.get(s, {}).get("descricao", s))
            )

    sancoes = query_df(
        con,
        """
        SELECT tipo_sancao, orgao_sancionador, data_inicio, data_fim, fonte
          FROM sancoes WHERE cnpj = ? ORDER BY data_inicio DESC NULLS LAST
        """,
        [cnpj],
    )
    contratos = query_df(
        con,
        """
        SELECT orgao, municipio, modalidade, objeto, valor_contrato, data_contrato,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade
          FROM contratos
         WHERE cnpj_fornecedor = ?
         ORDER BY valor_contrato DESC NULLS LAST
         LIMIT 100
        """,
        [cnpj],
    )
    socios = query_df(
        con,
        """
        SELECT nome_socio, doc_socio, qualificacao, data_entrada
          FROM socios WHERE cnpj = ? ORDER BY data_entrada DESC NULLS LAST LIMIT 30
        """,
        [cnpj],
    )
    return {
        "cnpj": cnpj,
        "empresa": empresa,
        "score": score,
        "eventos": eventos,
        "sancoes": sancoes,
        "contratos": contratos,
        "socios": socios,
    }


def municipios(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Lista de municípios disponíveis para a busca da página principal."""
    return query_df(
        con,
        """
        SELECT DISTINCT municipio
          FROM contratos
         WHERE municipio IS NOT NULL
         ORDER BY municipio
        """,
    )["municipio"].tolist()


def licitacoes_por_municipio(
    con: duckdb.DuckDBPyConnection,
    status: DatabaseStatus,
    municipio: str,
    *,
    ordem: str = "score",
    limit: int | None = None,
) -> pd.DataFrame:
    """Licitações de um município, 1 linha por chave composta.

    Agrupa a base de contratos pela chave da licitação e traz a razão social da
    empresa vencedora (via `cnpj_vencedor`) e, quando disponível, o score da
    licitação. Ordena por score por padrão, com alternativas seguras por data,
    valor ou participantes. Sem `limit`, devolve TODAS as licitações da cidade.
    """
    # A busca municipal deve incluir processos sem vencedor. A view de
    # homologados exclui esses casos, por isso esta consulta parte da tabela
    # completa e agrega o score separadamente pela chave da licitação.
    base_relation = "contratos"
    order_by = ORDENS_LICITACAO.get(ordem, ORDENS_LICITACAO["score"])
    if has_licitacao_scores(status):
        score_columns = """
               (sl.entidade_id IS NOT NULL) AS tem_score,
               sl.score,
               sl.score_bruto,
               sl.qtd_sinais,
               sl.sinais
        """
        score_join = """
          LEFT JOIN scores_licitacao sl
            ON sl.cd_orgao = l.cd_orgao
           AND sl.nr_licitacao = l.nr_licitacao
           AND sl.ano_licitacao = l.ano_licitacao
           AND sl.cd_tipo_modalidade = l.cd_tipo_modalidade
        """
    else:
        score_columns = """
               FALSE AS tem_score,
               NULL::INTEGER AS score,
               NULL::INTEGER AS score_bruto,
               0::INTEGER AS qtd_sinais,
               NULL::VARCHAR AS sinais
        """
        score_join = ""
    params: list[Any] = [municipio]
    clausula_limit = ""
    if limit is not None:
        clausula_limit = "LIMIT ?"
        params.append(limit)
    return query_df(
        con,
        f"""
        WITH licitacoes AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   ANY_VALUE(orgao)              AS orgao,
                   ANY_VALUE(modalidade)         AS modalidade,
                   ANY_VALUE(objeto)             AS objeto,
                   MAX(valor_contrato)           AS valor_contrato,
                   MAX(data_contrato)            AS data_contrato,
                   MAX(qtd_participantes)        AS qtd_participantes,
                   ANY_VALUE(cnpj_vencedor)      AS cnpj_vencedor,
                   BOOL_OR(flag_covid)           AS flag_covid
              FROM {base_relation}
             WHERE municipio = ?
               AND cd_orgao IS NOT NULL
             GROUP BY cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade
        )
        SELECT l.*, e.razao_social AS razao_vencedor,
               {score_columns}
          FROM licitacoes l
          LEFT JOIN empresas e ON e.cnpj = l.cnpj_vencedor
          {score_join}
         ORDER BY {order_by}
         {clausula_limit}
        """,
        params,
    )


def contratos_da_licitacao(
    con: duckdb.DuckDBPyConnection,
    chave: dict[str, str],
) -> pd.DataFrame:
    """Todas as linhas de `contratos` (fornecedores participantes) de uma licitação."""
    where, params = _chave_where(chave)
    return query_df(
        con,
        f"""
        SELECT cnpj_fornecedor, razao_social, modalidade,
               valor_contrato, data_contrato, numero_contrato
          FROM contratos
         WHERE {where}
         ORDER BY valor_contrato DESC NULLS LAST
        """,
        params,
    )


def _chave_where(chave: dict[str, str], *, alias: str = "") -> tuple[str, list[Any]]:
    """Cláusula WHERE para a chave composta da licitação (com alias opcional)."""
    prefixo = f"{alias}." if alias else ""
    clauses = [f"{prefixo}{col} = ?" for col in CHAVE_LICITACAO]
    params = [chave[col] for col in CHAVE_LICITACAO]
    return " AND ".join(clauses), params


def propostas_concorrentes(
    con: duckdb.DuckDBPyConnection,
    chave: dict[str, str],
    cnpj_vencedor: str | None,
) -> pd.DataFrame:
    """Propostas das empresas que concorreram na licitação e NÃO venceram.

    Lista ordenada do menor ao maior valor. Exclui o `cnpj_vencedor` (quando
    conhecido) para sobrar só as perdedoras.
    """
    where, params = _chave_where(chave, alias="p")
    if cnpj_vencedor:
        where += " AND (p.cnpj_proposta IS NULL OR p.cnpj_proposta <> ?)"
        params.append(cnpj_vencedor)
    return query_df(
        con,
        f"""
        SELECT p.cnpj_proposta,
               e.razao_social,
               p.resultado_proposta,
               p.valor_total_proposta,
               p.percentual_desconto,
               p.data_proposta
          FROM propostas p
          LEFT JOIN empresas e ON e.cnpj = p.cnpj_proposta
         WHERE {where}
         ORDER BY p.valor_total_proposta ASC NULLS LAST
        """,
        params,
    )


def licitacao_detalhe(
    con: duckdb.DuckDBPyConnection,
    status: DatabaseStatus,
    chave: dict[str, str],
) -> dict[str, Any]:
    """Dados do dossiê de uma licitação: cabeçalho, vencedora, sanções, sinais e perdedoras."""
    where, params = _chave_where(chave)
    cabecalho = query_df(
        con,
        f"""
        SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               ANY_VALUE(orgao)         AS orgao,
               ANY_VALUE(municipio)     AS municipio,
               ANY_VALUE(modalidade)    AS modalidade,
               ANY_VALUE(objeto)        AS objeto,
               MAX(valor_contrato)      AS valor_contrato,
               MAX(data_contrato)       AS data_contrato,
               MAX(qtd_participantes)   AS qtd_participantes,
               BOOL_OR(flag_covid)      AS flag_covid,
               ANY_VALUE(cnpj_vencedor) AS cnpj_vencedor,
               ANY_VALUE(numero_contrato) AS numero_contrato
          FROM contratos
         WHERE {where}
         GROUP BY cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade
        """,
        params,
    )

    cnpj_vencedor = None
    if not cabecalho.empty and pd.notna(cabecalho.iloc[0]["cnpj_vencedor"]):
        cnpj_vencedor = str(cabecalho.iloc[0]["cnpj_vencedor"])

    empresa = pd.DataFrame()
    sancoes = pd.DataFrame()
    if cnpj_vencedor:
        empresa = query_df(con, "SELECT * FROM empresas WHERE cnpj = ? LIMIT 1", [cnpj_vencedor])
        sancoes = query_df(
            con,
            """
            SELECT tipo_sancao, orgao_sancionador, data_inicio, data_fim, fonte
              FROM sancoes
             WHERE cnpj = ?
             ORDER BY data_inicio DESC NULLS LAST
            """,
            [cnpj_vencedor],
        )

    perdedoras = propostas_concorrentes(con, chave, cnpj_vencedor)
    participantes = contratos_da_licitacao(con, chave)
    sinais = _sinais_licitacao(con, status, chave, cabecalho, empresa, sancoes)

    return {
        "cabecalho": cabecalho,
        "empresa": empresa,
        "sancoes": sancoes,
        "contratos": participantes,
        "perdedoras": perdedoras,
        "sinais": sinais,
        "cnpj_vencedor": cnpj_vencedor,
    }


def _sinais_licitacao(
    con: duckdb.DuckDBPyConnection,
    status: DatabaseStatus,
    chave: dict[str, str],
    cabecalho: pd.DataFrame,
    empresa: pd.DataFrame,
    sancoes: pd.DataFrame,
) -> list[str]:
    """Frases de indício (linguagem de hipótese) para a licitação selecionada."""
    sinais: list[str] = []

    def _existe(relation: str) -> bool:
        if not relation_exists(status, relation):
            return False
        where, params = _chave_where(chave)
        n = query_df(
            con, f"SELECT COUNT(*) AS n FROM {relation} WHERE {where}", params
        ).iloc[0]["n"]
        return int(n) > 0

    if _existe("vw_proposta_unica"):
        sinais.append("Apenas uma proposta classificada após desclassificações (competição mínima).")
    if relation_exists(status, "vw_cover_bidding_indicios"):
        where, params = _chave_where(chave)
        cover = query_df(
            con,
            f"SELECT MAX(razao_2a_vs_1a) AS razao FROM vw_cover_bidding_indicios WHERE {where}",
            params,
        )
        razao = cover.iloc[0]["razao"] if not cover.empty else None
        if razao is not None and pd.notna(razao):
            sinais.append(
                f"Segunda proposta {float(razao):.1f}x maior que a vencedora (padrão de cover bidding)."
            )
    if _existe("vw_alteracao_apos_abertura"):
        sinais.append("Edital alterado/republicado após a publicação inicial.")
    if relation_exists(status, "vw_sobrepreco_indicios"):
        where, params = _chave_where(chave)
        sobre = query_df(
            con,
            f"SELECT MAX(razao_vs_mediana) AS razao FROM vw_sobrepreco_indicios WHERE {where}",
            params,
        )
        razao = sobre.iloc[0]["razao"] if not sobre.empty else None
        if razao is not None and pd.notna(razao):
            sinais.append(
                f"Item com preço até {float(razao):.1f}x a mediana do grupo comparável."
            )

    if not cabecalho.empty:
        qtd = cabecalho.iloc[0]["qtd_participantes"]
        if qtd is not None and pd.notna(qtd) and qtd <= 2:
            sinais.append("Baixa competição registrada (até dois participantes).")

    if not sancoes.empty:
        sinais.append("Empresa vencedora aparece em lista de sanções.")
    if not empresa.empty:
        emp = empresa.iloc[0]
        if emp.get("situacao_cadastral") is not None and str(emp.get("situacao_cadastral")) != "2":
            sinais.append("Situação cadastral da empresa vencedora não consta como ativa.")
        cap = emp.get("capital_social")
        valor = cabecalho.iloc[0]["valor_contrato"] if not cabecalho.empty else None
        if (
            cap is not None and pd.notna(cap) and float(cap) > 0
            and valor is not None and pd.notna(valor)
            and float(valor) / float(cap) > 10
        ):
            sinais.append("Valor do contrato é mais de 10x o capital social da vencedora.")

    return sinais


def filter_options(con: duckdb.DuckDBPyConnection) -> dict[str, list[str]]:
    """Small option lists for sidebar filters."""
    municipios = query_df(
        con,
        """
        SELECT DISTINCT municipio
          FROM contratos
         WHERE municipio IS NOT NULL
         ORDER BY municipio
         LIMIT 300
        """,
    )["municipio"].tolist()
    orgaos = query_df(
        con,
        """
        SELECT DISTINCT orgao
          FROM contratos
         WHERE orgao IS NOT NULL
         ORDER BY orgao
         LIMIT 500
        """,
    )["orgao"].tolist()
    return {"municipios": municipios, "orgaos": orgaos}


def redflag_counts(con: duckdb.DuckDBPyConnection, status: DatabaseStatus) -> pd.DataFrame:
    """Counts for the red flag strip on the first screen."""
    checks = [
        ("Contratos com sanção", "contrato", "vw_contratos_com_sancao", "SELECT COUNT(*) AS n FROM vw_contratos_com_sancao"),
        ("Itens com sobrepreço", "item", "vw_sobrepreco_indicios", "SELECT COUNT(*) AS n FROM vw_sobrepreco_indicios"),
        ("Licitações com proposta única", "licitação", "vw_proposta_unica", "SELECT COUNT(*) AS n FROM vw_proposta_unica"),
        ("Licitações com cover bidding", "licitação", "vw_cover_bidding_indicios", "SELECT COUNT(*) AS n FROM vw_cover_bidding_indicios"),
        ("Alterações após publicação", "evento", "vw_alteracao_apos_abertura", "SELECT COUNT(*) AS n FROM vw_alteracao_apos_abertura"),
    ]
    rows = []
    for label, scope, relation, sql in checks:
        rows.append(
            {
                "sinal": label,
                "escopo": scope,
                "registros": int(query_df(con, sql).iloc[0]["n"]) if relation_exists(status, relation) else 0,
                "disponivel": relation_exists(status, relation),
            }
        )
    return pd.DataFrame(rows)


def risk_queue(
    con: duckdb.DuckDBPyConnection,
    status: DatabaseStatus,
    filters: ContractFilters,
    *,
    limit: int = 200,
) -> pd.DataFrame:
    """Return contracts prioritized for review.

    Uses Pessoa 2's score view when present; otherwise uses a provisional score
    from existing schema and views.
    """
    if has_score_view(status):
        return _risk_queue_from_score_view(con, filters, limit=limit)
    return _risk_queue_fallback(con, status, filters, limit=limit)


def contract_detail(
    con: duckdb.DuckDBPyConnection,
    status: DatabaseStatus,
    cnpj_fornecedor: str,
    numero_contrato: str | None,
) -> dict[str, pd.DataFrame]:
    """Data frames used by the detail screen."""
    contrato = query_df(
        con,
        """
        SELECT *
          FROM contratos
         WHERE cnpj_fornecedor = ?
           AND (? IS NULL OR numero_contrato = ?)
         ORDER BY valor_contrato DESC NULLS LAST
         LIMIT 1
        """,
        [cnpj_fornecedor, numero_contrato, numero_contrato],
    )
    empresa = query_df(con, "SELECT * FROM empresas WHERE cnpj = ? LIMIT 1", [cnpj_fornecedor])
    socios = query_df(
        con,
        """
        SELECT nome_socio, doc_socio, tipo_socio, qualificacao, data_entrada
          FROM socios
         WHERE cnpj = ?
         ORDER BY data_entrada DESC NULLS LAST
         LIMIT 30
        """,
        [cnpj_fornecedor],
    )
    sancoes = query_df(
        con,
        """
        SELECT tipo_sancao, orgao_sancionador, data_inicio, data_fim, fonte
          FROM sancoes
         WHERE cnpj = ?
         ORDER BY data_inicio DESC NULLS LAST
        """,
        [cnpj_fornecedor],
    )
    itens = pd.DataFrame()
    if relation_exists(status, "itens"):
        itens = query_df(
            con,
            """
            SELECT descricao, unidade, quantidade, valor_unitario_homologado,
                   valor_total_homologado, flag_covid
              FROM itens
             WHERE cnpj_fornecedor = ?
             ORDER BY valor_total_homologado DESC NULLS LAST
             LIMIT 50
            """,
            [cnpj_fornecedor],
        )

    propostas = pd.DataFrame()
    if relation_exists(status, "propostas"):
        propostas = query_df(
            con,
            """
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   data_proposta, resultado_proposta, valor_total_proposta,
                   percentual_desconto, data_homologacao
              FROM propostas
             WHERE cnpj_proposta = ?
             ORDER BY valor_total_proposta DESC NULLS LAST
             LIMIT 50
            """,
            [cnpj_fornecedor],
        )

    sobrepreco = pd.DataFrame()
    if relation_exists(status, "vw_sobrepreco_indicios"):
        sobrepreco = query_df(
            con,
            """
            SELECT descricao, unidade, valor_unitario_homologado, mediana,
                   n_obs, razao_vs_mediana
              FROM vw_sobrepreco_indicios
             WHERE cnpj_fornecedor = ?
             ORDER BY razao_vs_mediana DESC
             LIMIT 30
            """,
            [cnpj_fornecedor],
        )

    return {
        "contrato": contrato,
        "empresa": empresa,
        "socios": socios,
        "sancoes": sancoes,
        "itens": itens,
        "propostas": propostas,
        "sobrepreco": sobrepreco,
    }


def licitation_signals(con: duckdb.DuckDBPyConnection, status: DatabaseStatus) -> dict[str, pd.DataFrame]:
    """Top records from licitation-level views that cannot be joined perfectly to contracts."""
    result: dict[str, pd.DataFrame] = {}
    if relation_exists(status, "vw_proposta_unica"):
        result["Proposta única"] = query_df(
            con,
            """
            SELECT *
              FROM vw_proposta_unica
             ORDER BY ano_licitacao DESC NULLS LAST
             LIMIT 30
            """,
        )
    if relation_exists(status, "vw_cover_bidding_indicios"):
        result["Cover bidding"] = query_df(
            con,
            """
            SELECT *
              FROM vw_cover_bidding_indicios
             ORDER BY razao_2a_vs_1a DESC NULLS LAST
             LIMIT 30
            """,
        )
    if relation_exists(status, "vw_alteracao_apos_abertura"):
        result["Alteração após publicação"] = query_df(
            con,
            """
            SELECT *
              FROM vw_alteracao_apos_abertura
             ORDER BY dias_apos_publicacao DESC NULLS LAST
             LIMIT 30
            """,
        )
    return result


def _where_clause(filters: ContractFilters, *, alias: str = "c") -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if filters.municipio:
        clauses.append(f"{alias}.municipio = ?")
        params.append(filters.municipio)
    if filters.orgao:
        clauses.append(f"{alias}.orgao = ?")
        params.append(filters.orgao)
    if filters.busca:
        clauses.append(
            f"({alias}.razao_social ILIKE ? OR {alias}.cnpj_fornecedor ILIKE ? OR {alias}.objeto ILIKE ?)"
        )
        term = f"%{filters.busca.strip()}%"
        params.extend([term, term, term])
    if filters.minimo_valor is not None and filters.minimo_valor > 0:
        clauses.append(f"{alias}.valor_contrato >= ?")
        params.append(filters.minimo_valor)
    if filters.apenas_covid:
        clauses.append(f"{alias}.flag_covid IS TRUE")
    return ("WHERE " + " AND ".join(clauses) if clauses else "", params)


def _risk_queue_from_score_view(
    con: duckdb.DuckDBPyConnection,
    filters: ContractFilters,
    *,
    limit: int,
) -> pd.DataFrame:
    where, params = _where_clause(filters, alias="s")
    params.append(limit)
    return query_df(
        con,
        f"""
        SELECT *
          FROM {SCORE_VIEW} s
          {where}
         ORDER BY score_risco DESC NULLS LAST, valor_contrato DESC NULLS LAST
         LIMIT ?
        """,
        params,
    )


def _risk_queue_fallback(
    con: duckdb.DuckDBPyConnection,
    status: DatabaseStatus,
    filters: ContractFilters,
    *,
    limit: int,
) -> pd.DataFrame:
    base_relation = _contracts_base(status)
    sobrepreco_cte = (
        """
        sobrepreco AS (
            SELECT cnpj_fornecedor,
                   COUNT(*) AS qtd_sobrepreco,
                   MAX(razao_vs_mediana) AS maior_razao_sobrepreco
              FROM vw_sobrepreco_indicios
             GROUP BY cnpj_fornecedor
        ),
        """
        if relation_exists(status, "vw_sobrepreco_indicios")
        else """
        sobrepreco AS (
            SELECT NULL::VARCHAR AS cnpj_fornecedor,
                   0 AS qtd_sobrepreco,
                   NULL::DOUBLE AS maior_razao_sobrepreco
             WHERE FALSE
        ),
        """
    )
    where, params = _where_clause(filters, alias="c")
    params.append(limit)
    return query_df(
        con,
        f"""
        WITH
        sancoes_agregadas AS (
            SELECT cnpj, COUNT(*) AS qtd_sancoes
              FROM sancoes
             GROUP BY cnpj
        ),
        sancoes_ativas AS (
            SELECT DISTINCT c.cnpj_fornecedor
              FROM {base_relation} c
              JOIN sancoes s ON s.cnpj = c.cnpj_fornecedor
             WHERE c.data_contrato BETWEEN COALESCE(s.data_inicio, DATE '1900-01-01')
                                       AND COALESCE(s.data_fim, DATE '2100-12-31')
        ),
        {sobrepreco_cte}
        base AS (
            SELECT c.cnpj_fornecedor,
                   c.razao_social,
                   c.orgao,
                   c.municipio,
                   c.modalidade,
                   c.objeto,
                   c.valor_contrato,
                   c.data_contrato,
                   c.numero_contrato,
                   c.qtd_participantes,
                   c.flag_covid,
                   e.data_abertura,
                   e.capital_social,
                   e.situacao_cadastral,
                   CASE
                       WHEN e.data_abertura IS NOT NULL
                        AND c.data_contrato IS NOT NULL
                        AND c.data_contrato - e.data_abertura < 180
                        AND c.valor_contrato > 100000
                       THEN TRUE ELSE FALSE
                   END AS indicio_empresa_jovem_contrato_grande,
                   CASE
                       WHEN e.situacao_cadastral IS NOT NULL
                        AND e.situacao_cadastral <> '2'
                       THEN TRUE ELSE FALSE
                   END AS indicio_empresa_inativa_com_contrato,
                   CASE
                       WHEN e.capital_social IS NOT NULL
                        AND e.capital_social > 0
                        AND c.valor_contrato / e.capital_social > 10
                       THEN TRUE ELSE FALSE
                   END AS indicio_capital_baixo,
                   COALESCE(sa.qtd_sancoes, 0) AS qtd_sancoes,
                   sp.qtd_sobrepreco,
                   sp.maior_razao_sobrepreco,
                   (sat.cnpj_fornecedor IS NOT NULL) AS indicio_sancionado_ativo
              FROM {base_relation} c
              LEFT JOIN empresas e ON e.cnpj = c.cnpj_fornecedor
              LEFT JOIN sancoes_agregadas sa ON sa.cnpj = c.cnpj_fornecedor
              LEFT JOIN sancoes_ativas sat ON sat.cnpj_fornecedor = c.cnpj_fornecedor
              LEFT JOIN sobrepreco sp ON sp.cnpj_fornecedor = c.cnpj_fornecedor
              {where}
        )
        SELECT *,
               LEAST(
                   100,
                   CASE WHEN indicio_sancionado_ativo THEN 30 ELSE 0 END
                   + CASE WHEN qtd_sancoes > 0 AND NOT indicio_sancionado_ativo THEN 12 ELSE 0 END
                   + CASE WHEN indicio_empresa_inativa_com_contrato THEN 22 ELSE 0 END
                   + CASE WHEN indicio_empresa_jovem_contrato_grande THEN 10 ELSE 0 END
                   + CASE WHEN indicio_capital_baixo THEN 8 ELSE 0 END
                   + CASE WHEN qtd_participantes <= 1 THEN 22 WHEN qtd_participantes <= 2 THEN 6 ELSE 0 END
                   + CASE WHEN COALESCE(maior_razao_sobrepreco, 0) >= 5 THEN 18
                          WHEN COALESCE(maior_razao_sobrepreco, 0) >= 3 THEN 6
                          ELSE 0 END
                   + CASE WHEN flag_covid AND COALESCE(qtd_sobrepreco, 0) > 0 THEN 10 ELSE 0 END
               ) AS score_provisorio
          FROM base
         ORDER BY score_provisorio DESC, valor_contrato DESC NULLS LAST
         LIMIT ?
        """,
        params,
    )


def _contracts_base(status: DatabaseStatus) -> str:
    """Use the documented default base when available."""
    return "vw_contratos_homologados" if relation_exists(status, "vw_contratos_homologados") else "contratos"
