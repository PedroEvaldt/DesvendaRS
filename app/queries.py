"""SQL queries used by the demo-first Streamlit app.

The database does not preserve the full licitation key on `contratos`, so the
fallback risk queue intentionally mixes contract-level and supplier-level
signals. Labels in the UI should describe those as indications for review.
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
