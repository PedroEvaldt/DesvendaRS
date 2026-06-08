"""Testes do site FastAPI contra o mock DuckDB (com tabelas de score)."""
from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient

from scripts.create_mock_db import main as criar_mock


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Sobe o app apontando DESVENDARS_DB para um mock recém-criado."""
    db_path = tmp_path_factory.mktemp("web") / "mock.duckdb"
    argv = sys.argv
    sys.argv = ["create_mock_db.py", "--path", str(db_path), "--force"]
    try:
        criar_mock()
    finally:
        sys.argv = argv

    import web.main as web_main

    web_main = importlib.reload(web_main)
    web_main.os.environ["DESVENDARS_DB"] = str(db_path)
    with TestClient(web_main.app) as c:
        yield c
    web_main.os.environ.pop("DESVENDARS_DB", None)


def test_home_lista_empresas_por_red_flag(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "MEDSUL" in r.text
    assert "Score" in r.text


def test_busca_empresa_na_home(client):
    r = client.get("/", params={"q": "MEDSUL"})
    assert r.status_code == 200
    assert "MEDSUL" in r.text
    assert "ALFA OBRAS" not in r.text  # filtrou


def test_dossie_empresa_mostra_sinais_com_evidencia(client):
    r = client.get("/empresas/12345678000195")
    assert r.status_code == 200
    assert "Red flags" in r.text
    # descrição humana de um sinal de MEDSUL
    assert "sancao" in r.text.lower() or "sanção" in r.text.lower()


def test_busca_licitacoes_por_cidade(client):
    r = client.get("/licitacoes", params={"municipio": "PELOTAS"})
    assert r.status_code == 200
    assert "BETA TECNOLOGIA" in r.text
    assert "Score" in r.text
    assert "3 sinais" in r.text


def test_busca_licitacoes_permite_alternar_ordenacao(client):
    r = client.get(
        "/licitacoes",
        params={"municipio": "PELOTAS", "ordem": "participantes"},
    )
    assert r.status_code == 200
    assert 'value="participantes" selected' in r.text
    assert "Ordenadas pela maior quantidade de participantes" in r.text


def test_licitacao_sem_vencedor_tem_link_e_dossie(client):
    lista = client.get("/licitacoes", params={"municipio": "BAGE"})
    assert lista.status_code == 200
    assert "Licitação 500/2026" in lista.text
    assert "Vencedora não identificada" in lista.text
    assert 'data-href="/licitacoes/005/500/2026/PRI"' in lista.text

    detalhe = client.get("/licitacoes/005/500/2026/PRI")
    assert detalhe.status_code == 200
    assert "Aquisicao de equipamentos" in detalhe.text
    assert "Vencedora não identificada" in detalhe.text
    assert 'href="/empresas/None"' not in detalhe.text


def test_dossie_licitacao_mostra_vencedora_e_perdedoras(client):
    r = client.get("/licitacoes/003/300/2026/PRE")
    assert r.status_code == 200
    assert "BETA TECNOLOGIA" in r.text          # vencedora
    assert "DELTA SOLUCOES" in r.text           # participante/perdedora
    assert "EPSILON SISTEMAS" in r.text         # perdedora


def test_home_mostra_panorama_e_metodologia(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Panorama de risco" in r.text
    assert "Distribuição dos scores" in r.text
    assert "Órgãos mais monitorados" in r.text
    assert "Municípios mais monitorados" in r.text
    assert "Como o score de risco é calculado?" in r.text


def test_dossie_licitacao_mostra_gauge_alertas_e_timeline(client):
    r = client.get("/licitacoes/003/300/2026/PRE")
    assert r.status_code == 200
    assert "Score de risco" in r.text          # gauge
    assert "/100" in r.text
    assert "Alertas para revisão" in r.text     # painel de severidade
    assert "Linha do tempo" in r.text           # timeline
    assert "Publicação do edital" in r.text
    # postura de indício preservada (linguagem de hipótese, não de acusação)
    assert "análise humana" in r.text.lower()
    assert "explicação legítima" in r.text.lower()


def test_healthz(client):
    assert client.get("/healthz").text == "ok"
