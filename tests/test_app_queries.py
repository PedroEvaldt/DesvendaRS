"""Tests for the Streamlit app query helpers."""
from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from app import queries
from app.db import DatabaseStatus, inspect_database
from app.queries import ContractFilters, has_score_view
from scripts.create_mock_db import main as criar_mock


def test_detecta_view_de_score_quando_disponivel(tmp_path):
    status = DatabaseStatus(
        path=tmp_path / "dados.duckdb",
        exists=True,
        tables={"contratos"},
        views={"vw_score_contratos"},
    )
    assert has_score_view(status)


def test_nao_detecta_view_de_score_quando_ausente(tmp_path):
    status = DatabaseStatus(
        path=tmp_path / "dados.duckdb",
        exists=True,
        tables={"contratos"},
        views={"vw_contratos_com_sancao"},
    )
    assert not has_score_view(status)


def test_contract_filters_defaults_are_non_restrictive():
    filters = ContractFilters()
    assert filters.municipio is None
    assert filters.orgao is None
    assert filters.busca is None
    assert filters.minimo_valor is None
    assert filters.apenas_covid is False


@pytest.fixture(scope="module")
def mock_db(tmp_path_factory):
    """Constrói o mock DB e devolve (conexão read-only, status)."""
    db_path = tmp_path_factory.mktemp("db") / "mock.duckdb"
    import sys

    argv = sys.argv
    sys.argv = ["create_mock_db.py", "--path", str(db_path), "--force"]
    try:
        criar_mock()
    finally:
        sys.argv = argv
    status = inspect_database(db_path)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        yield con, status
    finally:
        con.close()


def test_licitacoes_por_municipio_traz_vencedora(mock_db):
    con, status = mock_db
    df = queries.licitacoes_por_municipio(con, status, "PELOTAS")
    assert len(df) == 1
    linha = df.iloc[0]
    assert linha["cd_orgao"] == "003"
    assert linha["nr_licitacao"] == "300"
    assert linha["cnpj_vencedor"] == "32345678000195"
    assert linha["razao_vencedor"] == "BETA TECNOLOGIA PUBLICA SA"


def test_licitacoes_por_municipio_traz_score_da_licitacao(mock_db):
    con, status = mock_db
    df = queries.licitacoes_por_municipio(con, status, "PELOTAS")
    linha = df.iloc[0]
    assert linha["tem_score"]
    assert linha["score"] > 0
    assert linha["qtd_sinais"] > 0
    assert linha["sinais"]


def test_licitacao_sem_vencedor_permanece_na_listagem(mock_db):
    con, status = mock_db
    df = queries.licitacoes_por_municipio(con, status, "BAGE")
    assert len(df) == 1
    linha = df.iloc[0]
    assert linha["nr_licitacao"] == "500"
    assert pd.isna(linha["cnpj_vencedor"])
    assert pd.isna(linha["razao_vencedor"])


def test_dossie_licitacao_sem_vencedor_mantem_dados_do_processo(mock_db):
    con, status = mock_db
    chave = {
        "cd_orgao": "005",
        "nr_licitacao": "500",
        "ano_licitacao": "2026",
        "cd_tipo_modalidade": "PRI",
    }
    detalhe = queries.licitacao_detalhe(con, status, chave)
    assert not detalhe["cabecalho"].empty
    assert detalhe["cabecalho"].iloc[0]["municipio"] == "BAGE"
    assert detalhe["cnpj_vencedor"] is None
    assert detalhe["empresa"].empty


def test_licitacoes_por_municipio_funciona_sem_tabela_de_score(mock_db):
    con, status = mock_db
    status_sem_score = DatabaseStatus(
        path=status.path,
        exists=status.exists,
        tables=status.tables - {"scores_licitacao"},
        views=status.views,
    )
    linha = queries.licitacoes_por_municipio(
        con, status_sem_score, "PELOTAS"
    ).iloc[0]
    assert not linha["tem_score"]
    assert pd.isna(linha["score"])
    assert linha["qtd_sinais"] == 0


@pytest.mark.parametrize(
    ("ordem", "trecho_sql"),
    [
        ("score", "score DESC NULLS LAST"),
        ("data", "l.data_contrato DESC NULLS LAST"),
        ("valor", "l.valor_contrato DESC NULLS LAST"),
        ("participantes", "l.qtd_participantes DESC NULLS LAST"),
    ],
)
def test_licitacoes_por_municipio_aplica_ordenacao(
    mock_db, monkeypatch, ordem, trecho_sql
):
    con, status = mock_db
    sql_executado = ""
    query_df_original = queries.query_df

    def capturar_sql(conexao, sql, params=None):
        nonlocal sql_executado
        sql_executado = sql
        return query_df_original(conexao, sql, params)

    monkeypatch.setattr(queries, "query_df", capturar_sql)
    queries.licitacoes_por_municipio(con, status, "PELOTAS", ordem=ordem)
    assert trecho_sql in sql_executado


def test_licitacoes_por_municipio_ordem_invalida_volta_para_score(
    mock_db, monkeypatch
):
    con, status = mock_db
    sql_executado = ""
    query_df_original = queries.query_df

    def capturar_sql(conexao, sql, params=None):
        nonlocal sql_executado
        sql_executado = sql
        return query_df_original(conexao, sql, params)

    monkeypatch.setattr(queries, "query_df", capturar_sql)
    queries.licitacoes_por_municipio(con, status, "PELOTAS", ordem="invalida")
    assert "ORDER BY score DESC NULLS LAST" in sql_executado


def test_propostas_concorrentes_exclui_vencedora(mock_db):
    con, _ = mock_db
    chave = {
        "cd_orgao": "003",
        "nr_licitacao": "300",
        "ano_licitacao": "2026",
        "cd_tipo_modalidade": "PRE",
    }
    df = queries.propostas_concorrentes(con, chave, "32345678000195")
    cnpjs = list(df["cnpj_proposta"])
    assert cnpjs == ["52345678000195", "62345678000195"]  # ordenado por valor crescente
    assert "32345678000195" not in cnpjs


def test_licitacao_detalhe_monta_dossie(mock_db):
    con, status = mock_db
    chave = {
        "cd_orgao": "003",
        "nr_licitacao": "300",
        "ano_licitacao": "2026",
        "cd_tipo_modalidade": "PRE",
    }
    detalhe = queries.licitacao_detalhe(con, status, chave)
    assert detalhe["cnpj_vencedor"] == "32345678000195"
    assert not detalhe["cabecalho"].empty
    assert not detalhe["empresa"].empty
    assert not detalhe["contratos"].empty
    assert len(detalhe["perdedoras"]) == 2
    # cover bidding (250k/100k = 2.5x >= 2) deve gerar um indício
    assert any("cover bidding" in s.lower() for s in detalhe["sinais"])


def test_contratos_da_licitacao_lista_participantes(mock_db):
    con, _ = mock_db
    chave = {
        "cd_orgao": "003",
        "nr_licitacao": "300",
        "ano_licitacao": "2026",
        "cd_tipo_modalidade": "PRE",
    }
    df = queries.contratos_da_licitacao(con, chave)
    cnpjs = set(df["cnpj_fornecedor"])
    assert cnpjs == {"32345678000195", "52345678000195"}  # vencedora BETA + participante DELTA


def test_licitacoes_por_municipio_agrupa_participantes(mock_db):
    """Mesmo com 2 participantes, PELOTAS continua com 1 licitação na lista."""
    con, status = mock_db
    df = queries.licitacoes_por_municipio(con, status, "PELOTAS")
    assert len(df) == 1


def test_top_empresas_risco_ordena_por_red_flags(mock_db):
    con, status = mock_db
    df = queries.top_empresas_risco(con, status, limit=10)
    assert not df.empty
    # MEDSUL acumula mais sinais que ALFA
    assert df.iloc[0]["cnpj"] == "12345678000195"
    assert df.iloc[0]["qtd_sinais"] >= df.iloc[-1]["qtd_sinais"]
    assert df.iloc[0]["razao_social"] == "MEDSUL SUPRIMENTOS HOSPITALARES LTDA"


def test_top_empresas_risco_filtra_por_busca(mock_db):
    con, status = mock_db
    df = queries.top_empresas_risco(con, status, busca="MEDSUL")
    assert set(df["cnpj"]) == {"12345678000195"}


def test_empresa_dossie_traz_sinais_com_descricao(mock_db):
    con, status = mock_db
    dossie = queries.empresa_dossie(con, status, "12345678000195")
    assert not dossie["empresa"].empty
    assert not dossie["score"].empty
    assert not dossie["eventos"].empty
    assert "descricao" in dossie["eventos"].columns
    assert not dossie["sancoes"].empty


CHAVE_PELOTAS = {
    "cd_orgao": "003",
    "nr_licitacao": "300",
    "ano_licitacao": "2026",
    "cd_tipo_modalidade": "PRE",
}


def test_score_licitacao_traz_score_pela_chave(mock_db):
    con, status = mock_db
    df = queries.score_licitacao(con, status, CHAVE_PELOTAS)
    assert not df.empty
    linha = df.iloc[0]
    assert linha["score"] > 0
    assert linha["qtd_sinais"] >= 1


def test_alertas_licitacao_tem_severidade_descricao_evidencia(mock_db):
    con, status = mock_db
    df = queries.alertas_licitacao(con, status, CHAVE_PELOTAS)
    assert not df.empty
    for coluna in ("descricao", "evidencia", "severidade", "forca"):
        assert coluna in df.columns
    assert set(df["severidade"]).issubset({"alto", "medio", "baixo"})
    # cover bidding é um dos alertas dessa licitação
    assert df["sinal"].str.contains("cover_bidding").any()


def test_timeline_licitacao_ordenada_por_data(mock_db):
    con, status = mock_db
    etapas = queries.timeline_licitacao(con, status, CHAVE_PELOTAS)
    assert [e["etapa"] for e in etapas][0] == "Publicação do edital"
    assert any(e["etapa"] == "Contratação" for e in etapas)
    datas = [e["data"] for e in etapas]
    assert datas == sorted(datas)  # cronológica


def test_distribuicao_scores_devolve_dez_faixas(mock_db):
    con, status = mock_db
    df = queries.distribuicao_scores(con, status)
    assert list(df["faixa"]) == list(range(0, 100, 10))
    assert df["n"].sum() > 0


def test_distribuicao_scores_inclui_limite_superior_na_faixa_90(tmp_path):
    con = duckdb.connect()
    con.execute("CREATE TABLE scores_licitacao (score INTEGER)")
    con.execute("INSERT INTO scores_licitacao VALUES (90), (95), (99), (100)")
    status = DatabaseStatus(
        path=tmp_path / "mock.duckdb",
        exists=True,
        tables={"scores_licitacao"},
        views=set(),
    )
    try:
        df = queries.distribuicao_scores(con, status)
    finally:
        con.close()

    faixa_90 = df.loc[df["faixa"] == 90, "n"].item()
    assert faixa_90 == 4
    assert df["n"].sum() == 4


def test_orgaos_mais_alertas_ordena_desc(mock_db):
    con, status = mock_db
    df = queries.orgaos_mais_alertas(con, status)
    assert not df.empty
    assert {"orgao", "qtd_alertas"}.issubset(df.columns)
    assert list(df["qtd_alertas"]) == sorted(df["qtd_alertas"], reverse=True)


def test_municipios_mais_alertas_traz_pelotas(mock_db):
    con, status = mock_db
    df = queries.municipios_mais_alertas(con, status)
    assert not df.empty
    assert "PELOTAS" in set(df["municipio"])
    assert list(df["qtd_alertas"]) == sorted(df["qtd_alertas"], reverse=True)


def test_panorama_degrada_sem_tabelas_de_score(mock_db):
    con, status = mock_db
    sem_score = DatabaseStatus(
        path=status.path,
        exists=status.exists,
        tables=status.tables - {"scores_licitacao"},
        views=status.views,
    )
    assert queries.distribuicao_scores(con, sem_score)["n"].sum() == 0
    assert queries.orgaos_mais_alertas(con, sem_score).empty
    assert queries.municipios_mais_alertas(con, sem_score).empty
