"""Loader da tabela `itens` — base da análise de sobrepreço.

Granularidade: 1 linha por (CD_ORGAO, NR_LICITACAO, ANO_LICITACAO,
CD_TIPO_MODALIDADE, NR_LOTE, NR_ITEM).

`item.csv` tem o par TP_DOCUMENTO/NR_DOCUMENTO duplicado (mesma estrutura do
licitante.csv): o primeiro par é PJ (fornecedor do item, ~28% preenchido) e
o segundo é PF (representante). Aqui só nos interessa o CNPJ do fornecedor.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

import config
from etl.normalize import (
    limpar_cnpj,
    limpar_valor,
    normalizar_descricao_item,
    normalizar_texto,
)

log = logging.getLogger(__name__)


def _para_bool(valor: object) -> bool | None:
    if valor is None or (isinstance(valor, float) and valor != valor):
        return None
    s = str(valor).strip().upper()
    if s in {"S", "SIM", "TRUE", "T", "1"}:
        return True
    if s in {"N", "NAO", "NÃO", "FALSE", "F", "0"}:
        return False
    return None


def load_itens(path: Path = config.CSV_ITENS) -> pd.DataFrame:
    """Lê `item.csv` e devolve DataFrame no esquema `itens`."""
    log.info("Lendo %s", path.name)
    df = pd.read_csv(
        path,
        dtype=str,
        encoding="utf-8-sig",
        low_memory=False,
    )
    log.info("  %s linhas lidas", f"{len(df):,}".replace(",", "."))

    # Filtra CNPJ do fornecedor (par primário, PJ). O par .1 é PF — descartar.
    cnpj_eh_pj = df["TP_DOCUMENTO"] == "J"
    df["cnpj_fornecedor"] = df["NR_DOCUMENTO"].where(cnpj_eh_pj).map(limpar_cnpj)

    saida = pd.DataFrame(
        {
            "cd_orgao": df["CD_ORGAO"].map(normalizar_texto),
            "nr_licitacao": df["NR_LICITACAO"].map(normalizar_texto),
            "ano_licitacao": df["ANO_LICITACAO"].map(normalizar_texto),
            "cd_tipo_modalidade": df["CD_TIPO_MODALIDADE"].map(normalizar_texto),
            "nr_lote": df["NR_LOTE"].map(normalizar_texto),
            "nr_item": df["NR_ITEM"].map(normalizar_texto),
            "cnpj_fornecedor": df["cnpj_fornecedor"],
            "descricao": df["DS_ITEM"].map(normalizar_texto),
            "descricao_normalizada": df["DS_ITEM"].map(normalizar_descricao_item),
            "quantidade": df["QT_ITENS"].map(limpar_valor),
            "unidade": df["SG_UNIDADE_MEDIDA"].map(normalizar_texto),
            "valor_unitario_estimado": df["VL_UNITARIO_ESTIMADO"].map(limpar_valor),
            "valor_unitario_homologado": df["VL_UNITARIO_HOMOLOGADO"].map(limpar_valor),
            "valor_total_homologado": df["VL_TOTAL_HOMOLOGADO"].map(limpar_valor),
            "flag_covid": df["BL_COVID19"].map(_para_bool),
        }
    )

    # Dedup pela chave composta (alguma fonte pode duplicar; segura o esquema)
    chave = [
        "cd_orgao",
        "nr_licitacao",
        "ano_licitacao",
        "cd_tipo_modalidade",
        "nr_lote",
        "nr_item",
    ]
    antes = len(saida)
    saida = saida.drop_duplicates(subset=chave, keep="first")
    if antes != len(saida):
        log.info("  %s linhas duplicadas removidas pela chave composta", antes - len(saida))

    log.info("  %s linhas no resultado final", f"{len(saida):,}".replace(",", "."))
    return saida
