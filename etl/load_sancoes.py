"""Loader da tabela `sancoes` — empilha CEIS + CNEP + CFIL com coluna `fonte`.

CEIS e CNEP vêm do Portal da Transparência (federal), encoding cp1252, separador `;`.
CFIL/RS vem da Procuradoria-Geral do Estado do RS sem linha de cabeçalho: as posições
das colunas foram inferidas pela inspeção do `docs/inventario_fontes.md`.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

import config
from etl.normalize import limpar_cnpj, normalizar_texto, padronizar_data

log = logging.getLogger(__name__)


def _carregar_portal(path: Path, fonte: str) -> pd.DataFrame:
    """Lê CEIS ou CNEP (mesmo formato do Portal da Transparência)."""
    df = pd.read_csv(
        path,
        sep=";",
        encoding="cp1252",
        dtype=str,
        on_bad_lines="skip",
        engine="python",
    )
    # Só pessoa jurídica (CNPJ). PFs são descartadas — não há esquema para isso e LGPD.
    df = df[df["TIPO DE PESSOA"] == "J"].copy()
    saida = pd.DataFrame(
        {
            "cnpj": df["CPF OU CNPJ DO SANCIONADO"].map(limpar_cnpj),
            "tipo_sancao": df["CATEGORIA DA SANÇÃO"].map(normalizar_texto),
            "orgao_sancionador": df["ÓRGÃO SANCIONADOR"].map(normalizar_texto),
            "data_inicio": df["DATA INÍCIO SANÇÃO"].map(padronizar_data),
            "data_fim": df["DATA FINAL SANÇÃO"].map(padronizar_data),
            "fonte": fonte,
        }
    )
    return saida


def _carregar_cfil(path: Path) -> pd.DataFrame:
    """Lê SancoesCFIL-RS.csv (sem cabeçalho).

    Mapeamento de colunas (descoberto via inspeção):
      0 → órgão (ex.: 'Assembleia Legislativa')
      1 → suborgão
      2 → CNPJ ou CPF (string crua)
      3 → razão social
      12 → tipo de sanção (ex.: 'Suspensão/impedimento')
      13 → data início
      14 → data fim
    """
    df = pd.read_csv(
        path,
        sep=";",
        encoding="cp1252",
        dtype=str,
        header=None,
        on_bad_lines="skip",
        engine="python",
    )
    saida = pd.DataFrame(
        {
            "cnpj": df[2].map(limpar_cnpj),
            "tipo_sancao": df[12].map(normalizar_texto),
            "orgao_sancionador": df[0].map(normalizar_texto),
            "data_inicio": df[13].map(padronizar_data),
            "data_fim": df[14].map(padronizar_data),
            "fonte": "CFIL",
        }
    )
    return saida


def load_sancoes(
    ceis: Path = config.CSV_CEIS,
    cnep: Path = config.CSV_CNEP,
    cfil: Path = config.CSV_CFIL,
) -> pd.DataFrame:
    log.info("Lendo CEIS, CNEP, CFIL")
    partes = [
        _carregar_portal(ceis, "CEIS"),
        _carregar_portal(cnep, "CNEP"),
        _carregar_cfil(cfil),
    ]
    for nome, parte in zip(("CEIS", "CNEP", "CFIL"), partes):
        log.info("  %s: %s linhas (PJ)", nome, f"{len(parte):,}".replace(",", "."))

    df = pd.concat(partes, ignore_index=True)
    antes = len(df)
    df = df[df["cnpj"].notna()].copy()
    log.info("  %s linhas descartadas por CNPJ inválido/PF", antes - len(df))
    log.info("  %s linhas no resultado final", f"{len(df):,}".replace(",", "."))
    return df
