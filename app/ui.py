"""Presentation helpers for the Streamlit app."""
from __future__ import annotations

import pandas as pd
import streamlit as st


def configure_page() -> None:
    st.set_page_config(
        page_title="DesvendaRS",
        page_icon="DRS",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        :root {
            color-scheme: light;
            --desvenda-yellow: #F8BE14;
            --desvenda-red: #EA2048;
            --desvenda-green: #89C541;
            --desvenda-yellow-dark: #F5941F;
            --desvenda-red-dark: #9E2626;
            --desvenda-green-dark: #618927;
            --desvenda-ink: #241f1f;
            --desvenda-muted: #594f44;
            --desvenda-page: #fbfaf5;
            --desvenda-panel: #ffffff;
        }
        .stApp {
            background: var(--desvenda-page);
            color: var(--desvenda-ink);
        }
        .block-container {
            padding-top: 1.4rem;
        }
        h1, h2, h3, h4, h5, h6 {
            color: var(--desvenda-ink);
        }
        div[data-testid="stMetric"] {
            border: 1px solid rgba(158, 38, 38, 0.18);
            border-radius: 8px;
            padding: 0.85rem 0.9rem;
            background: var(--desvenda-panel);
            color: var(--desvenda-ink);
            box-shadow: inset 0 3px 0 var(--desvenda-yellow);
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricValue"],
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
            color: var(--desvenda-ink);
        }
        div[data-testid="stMetric"] [data-testid="stMetricDelta"] svg {
            fill: var(--desvenda-green-dark);
        }
        .signal {
            border-left: 4px solid var(--desvenda-red);
            background: #fff7e0;
            color: var(--desvenda-ink);
            padding: 0.65rem 0.8rem;
            border-radius: 6px;
            margin-bottom: 0.5rem;
        }
        .stAlert {
            color: var(--desvenda-ink);
        }
        div[data-testid="stSidebar"] {
            background: #fff8df;
            border-right: 1px solid rgba(245, 148, 31, 0.35);
        }
        div[data-testid="stSidebar"] * {
            color: var(--desvenda-ink);
        }
        .stButton > button,
        .stDownloadButton > button {
            background: var(--desvenda-red);
            color: #ffffff;
            border: 1px solid var(--desvenda-red-dark);
            border-radius: 6px;
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover {
            background: var(--desvenda-red-dark);
            color: #ffffff;
            border-color: var(--desvenda-red-dark);
        }
        .muted,
        .stCaptionContainer,
        div[data-testid="stMarkdownContainer"] p {
            color: var(--desvenda-muted);
        }
        div[data-baseweb="tab-list"] button {
            color: var(--desvenda-ink);
        }
        div[data-baseweb="tab-highlight"] {
            background-color: var(--desvenda-red);
        }
        div[data-baseweb="select"] * {
            color: var(--desvenda-ink);
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid rgba(97, 137, 39, 0.25);
            border-radius: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def money(value: object) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "R$ 0,00"
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def compact_number(value: object) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "0"
    return f"{int(value):,}".replace(",", ".")


def percent_level(score: object) -> str:
    try:
        score_f = float(score)
    except (TypeError, ValueError):
        return "Sem score"
    if score_f >= 70:
        return "Prioridade alta"
    if score_f >= 35:
        return "Prioridade média"
    if score_f > 0:
        return "Prioridade baixa"
    return "Sem indício automático"


def show_missing_database(path: object) -> None:
    st.title("DesvendaRS")
    st.subheader("Painel de revisão de contratos públicos")
    st.info(
        "O banco DuckDB ainda não foi encontrado. A interface já está pronta para "
        "ler o schema do projeto quando `db/dados.duckdb` existir."
    )
    st.code("uv run python -m etl.build_db", language="bash")
    st.caption(f"Caminho esperado: {path}")


def show_relation_warning(missing: set[str]) -> None:
    if missing:
        st.warning(
            "Banco encontrado, mas algumas relações esperadas não estão disponíveis: "
            + ", ".join(sorted(missing))
        )


def metric_row(metrics: dict) -> None:
    cols = st.columns(4)
    cols[0].metric("Contratos", compact_number(metrics.get("contratos", 0)))
    cols[1].metric("Valor contratado", money(metrics.get("valor_total", 0)))
    cols[2].metric("Fornecedores", compact_number(metrics.get("fornecedores", 0)))
    cols[3].metric("Fornecedores com sanção", compact_number(metrics.get("fornecedores_sancionados", 0)))


def signal_strip(df: pd.DataFrame) -> None:
    cols = st.columns(len(df) if len(df) > 0 else 1)
    for col, (_, row) in zip(cols, df.iterrows()):
        status = f"escopo: {row['escopo']}" if row["disponivel"] else "indisponível"
        col.metric(row["sinal"], compact_number(row["registros"]), status)


def format_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with friendlier display for known numeric columns."""
    out = df.copy()
    for col in out.columns:
        if col.startswith("valor") or col in {"capital_social", "mediana"}:
            out[col] = out[col].map(money)
        if col.startswith("score"):
            out[col] = out[col].map(lambda v: "" if pd.isna(v) else int(v))
    return out
