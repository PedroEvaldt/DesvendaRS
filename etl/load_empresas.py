"""Loader da tabela `empresas` a partir de Dados-Empresas-RS.csv (Receita / CNPJ)."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

import config
from etl.normalize import (
    limpar_cnpj,
    limpar_valor,
    normalizar_texto,
    padronizar_data,
)

log = logging.getLogger(__name__)

COLUNAS_USADAS = [
    "cnpj",
    "razao_social",
    "data_abertura",
    "cnae",
    "capital_social",
    "situacao_cadastral",
    "porte",
    "tipo_logradouro",
    "logradouro",
    "numero",
    "bairro",
    "id_municipio",
]


def _montar_endereco(row: pd.Series) -> str | None:
    partes = [
        row.get("tipo_logradouro"),
        row.get("logradouro"),
        row.get("numero"),
        row.get("bairro"),
    ]
    partes_validas = [str(p).strip() for p in partes if p and not pd.isna(p)]
    if not partes_validas:
        return None
    return normalizar_texto(", ".join(partes_validas))


def load_empresas(path: Path = config.CSV_EMPRESAS) -> pd.DataFrame:
    """Lê o cadastro de empresas RS e devolve o DataFrame no esquema alvo."""
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

    df["razao_social"] = df["razao_social"].map(lambda v: normalizar_texto(v, upper=True))
    df["data_abertura"] = df["data_abertura"].map(padronizar_data)
    df["capital_social"] = df["capital_social"].map(limpar_valor)
    df["cnae"] = df["cnae"].map(normalizar_texto)
    df["situacao_cadastral"] = df["situacao_cadastral"].map(normalizar_texto)
    df["porte"] = df["porte"].map(normalizar_texto)

    df["endereco"] = df.apply(_montar_endereco, axis=1)
    df["municipio"] = df["id_municipio"].map(normalizar_texto)

    saida = df[
        [
            "cnpj",
            "razao_social",
            "data_abertura",
            "cnae",
            "capital_social",
            "situacao_cadastral",
            "porte",
            "endereco",
            "municipio",
        ]
    ].drop_duplicates(subset="cnpj")
    log.info("  %s linhas no resultado final", f"{len(saida):,}".replace(",", "."))
    return saida
