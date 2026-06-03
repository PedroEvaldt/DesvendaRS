"""Loader da tabela `socios` a partir de Socios-RS.csv (Receita / QSA).

**LGPD:** `doc_socio` vem da fonte já mascarado (`***NNNNNN**`). Manter como está —
nunca tentar desmascarar.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

import config
from etl.normalize import limpar_cnpj, normalizar_texto, padronizar_data

log = logging.getLogger(__name__)

COLUNAS_USADAS = [
    "cnpj",
    "nome_socio",
    "doc_socio",
    "tipo_socio",
    "qualificacao",
    "data_entrada",
]


def load_socios(path: Path = config.CSV_SOCIOS) -> pd.DataFrame:
    log.info("Lendo %s", path.name)
    df = pd.read_csv(
        path,
        dtype=str,
        usecols=COLUNAS_USADAS,
        encoding="utf-8-sig",
        low_memory=False,
    )
    log.info("  %s linhas lidas", f"{len(df):,}".replace(",", "."))

    df["cnpj"] = df["cnpj"].map(limpar_cnpj)
    nulos_cnpj = int(df["cnpj"].isna().sum())
    df = df[df["cnpj"].notna()].copy()
    log.info("  %s linhas descartadas por CNPJ inválido", nulos_cnpj)

    df["nome_socio"] = df["nome_socio"].map(lambda v: normalizar_texto(v, upper=True))
    # doc_socio mantido EXATAMENTE como vem (mascarado) — não normalizar caixa nem dígitos.
    df["tipo_socio"] = df["tipo_socio"].map(normalizar_texto)
    df["qualificacao"] = df["qualificacao"].map(normalizar_texto)
    df["data_entrada"] = df["data_entrada"].map(padronizar_data)

    saida = df[
        [
            "cnpj",
            "nome_socio",
            "doc_socio",
            "tipo_socio",
            "qualificacao",
            "data_entrada",
        ]
    ]
    log.info("  %s linhas no resultado final", f"{len(saida):,}".replace(",", "."))
    return saida
