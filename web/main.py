"""Aplicação FastAPI do site DesvendaRS.

Renderiza HTML no servidor (Jinja2) reaproveitando as queries de `app/queries.py`
e a camada DuckDB read-only de `app/db.py`. O banco é selecionado por
`DESVENDARS_DB` (ou `config.DB_PATH`), o que permite apontar para um mock nos testes.

Postura: o site levanta **indícios**, nunca acusações. Todos os rótulos usam
linguagem de hipótese; `doc_socio` é exibido mascarado (LGPD).
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
from app.ai_overview import generate_licitacao_overview
from app import queries
from app.db import DatabaseStatus, connect, inspect_database

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="DesvendaRS")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ---------------------------------------------------------------------------
# Formatação (linguagem/locale BR) — disponível nos templates como filtros.
# ---------------------------------------------------------------------------
def moeda(value: Any) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "R$ 0,00"
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def numero(value: Any) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "0"
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def cnpj(value: Any) -> str:
    digits = "".join(char for char in str(value or "") if char.isdigit())
    if len(digits) != 14:
        return str(value or "—")
    return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"


def data_br(value: Any) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "—"
    try:
        parsed = pd.to_datetime(value)
        return parsed.strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return str(value)


def situacao_cadastral(value: Any) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "Não informada"
    text = str(value).strip()
    code = text.zfill(2) if text.isdigit() else text
    return {
        "01": "Nula",
        "02": "Ativa",
        "03": "Suspensa",
        "04": "Inapta",
        "08": "Baixada",
    }.get(code, text)


def nivel(score: Any) -> str:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "sem-score"
    if s >= 70:
        return "alto"
    if s >= 35:
        return "medio"
    if s > 0:
        return "baixo"
    return "sem-indicio"


templates.env.filters["moeda"] = moeda
templates.env.filters["numero"] = numero
templates.env.filters["cnpj"] = cnpj
templates.env.filters["data_br"] = data_br
templates.env.filters["situacao_cadastral"] = situacao_cadastral
templates.env.filters["nivel"] = nivel


# ---------------------------------------------------------------------------
# Acesso ao banco
# ---------------------------------------------------------------------------
def _db_path() -> Path:
    return Path(os.environ.get("DESVENDARS_DB", str(config.DB_PATH)))


@contextmanager
def _conexao():
    """Abre conexão read-only e o status do banco; ambos None se o banco não existe."""
    path = _db_path()
    status = inspect_database(path)
    if not status.exists:
        yield None, status
        return
    con = connect(path)
    try:
        yield con, status
    finally:
        con.close()


def _registros(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [] if df is None or df.empty else df.to_dict(orient="records")


def _primeiro(df: pd.DataFrame) -> dict[str, Any] | None:
    return None if df is None or df.empty else df.iloc[0].to_dict()


def _fallback(request: Request, status: DatabaseStatus) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "indisponivel.html",
        {"caminho": str(status.path), "existe": status.exists},
        status_code=503,
    )


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------
@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"


@app.get("/", response_class=HTMLResponse)
def home(request: Request, q: str | None = None) -> HTMLResponse:
    with _conexao() as (con, status):
        if con is None or not status.ready:
            return _fallback(request, status)
        empresas = queries.top_empresas_risco(con, status, limit=50, busca=q)
        metricas = queries.overview(con, status)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "metricas": metricas,
                "empresas": _registros(empresas),
                "busca": q or "",
                "tem_score": queries.has_score_tables(status),
                "tem_panorama": queries.has_licitacao_scores(status),
                "distribuicao": _registros(queries.distribuicao_scores(con, status)),
                "top_orgaos": _registros(queries.orgaos_mais_alertas(con, status)),
                "top_municipios": _registros(queries.municipios_mais_alertas(con, status)),
            },
        )


@app.get("/empresas/{cnpj}", response_class=HTMLResponse)
def empresa(request: Request, cnpj: str) -> HTMLResponse:
    with _conexao() as (con, status):
        if con is None:
            return _fallback(request, status)
        dossie = queries.empresa_dossie(con, status, cnpj)
        return templates.TemplateResponse(
            request,
            "empresa.html",
            {
                "cnpj": cnpj,
                "empresa": _primeiro(dossie["empresa"]),
                "score": _primeiro(dossie["score"]),
                "eventos": _registros(dossie["eventos"]),
                "sancoes": _registros(dossie["sancoes"]),
                "contratos": _registros(dossie["contratos"]),
                "socios": _registros(dossie["socios"]),
            },
        )


@app.get("/licitacoes", response_class=HTMLResponse)
def licitacoes(
    request: Request,
    municipio: str | None = None,
    ordem: str = "score",
) -> HTMLResponse:
    ordem_selecionada = ordem if ordem in queries.ORDENS_LICITACAO else "score"
    with _conexao() as (con, status):
        if con is None or not status.ready:
            return _fallback(request, status)
        cidades = queries.municipios(con)
        lista: list[dict[str, Any]] = []
        if municipio:
            lista = _registros(
                queries.licitacoes_por_municipio(
                    con,
                    status,
                    municipio,
                    ordem=ordem_selecionada,
                )
            )
        return templates.TemplateResponse(
            request,
            "licitacoes.html",
            {
                "cidades": cidades,
                "municipio": municipio or "",
                "ordem": ordem_selecionada,
                "licitacoes": lista,
            },
        )


@app.get(
    "/licitacoes/{cd_orgao}/{nr_licitacao}/{ano_licitacao}/{cd_tipo_modalidade}",
    response_class=HTMLResponse,
)
def licitacao(
    request: Request,
    cd_orgao: str,
    nr_licitacao: str,
    ano_licitacao: str,
    cd_tipo_modalidade: str,
) -> HTMLResponse:
    chave = {
        "cd_orgao": cd_orgao,
        "nr_licitacao": nr_licitacao,
        "ano_licitacao": ano_licitacao,
        "cd_tipo_modalidade": cd_tipo_modalidade,
    }
    with _conexao() as (con, status):
        if con is None:
            return _fallback(request, status)
        detalhe = queries.licitacao_detalhe(con, status, chave)
        ai_context = queries.licitacao_ai_context(con, status, chave, detalhe)
        ai_overview = generate_licitacao_overview(
            ai_context,
            timeout=6.0,
            api_key="" if os.environ.get("PYTEST_CURRENT_TEST") else None,
        )
        return templates.TemplateResponse(
            request,
            "licitacao.html",
            {
                "chave": chave,
                "cabecalho": _primeiro(detalhe["cabecalho"]),
                "empresa": _primeiro(detalhe["empresa"]),
                "sinais": detalhe["sinais"],
                "alertas": _registros(detalhe["alertas"]),
                "score": _primeiro(detalhe["score"]),
                "timeline": detalhe["timeline"],
                "sancoes": _registros(detalhe["sancoes"]),
                "participantes": _registros(detalhe["contratos"]),
                "perdedoras": _registros(detalhe["perdedoras"]),
                "cnpj_vencedor": detalhe["cnpj_vencedor"],
                "ai_overview": ai_overview,
            },
        )
