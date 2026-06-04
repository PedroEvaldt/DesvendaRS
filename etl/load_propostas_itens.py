"""Loader da tabela `propostas_itens` a partir de item_prop.csv (LicitaCon).

Granularidade: 1 linha por (licitação × lote × item × fornecedor que propôs).
É a versão granular de `propostas` — permite comparar TODOS os preços
unitários propostos pelos concorrentes pro mesmo item, não só o vencedor
(que já está em `itens`).

Base para análise de:
- Cover bidding por item (perdedora propõe preço unitário artificialmente alto).
- Refinamento de `vw_sobrepreco_indicios` cruzando com classe da proposta.
"""
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


def load_propostas_itens(path: Path = config.CSV_ITEM_PROP) -> pd.DataFrame:
    log.info("Lendo %s", path.name)
    df = pd.read_csv(
        path,
        dtype=str,
        encoding="utf-8-sig",
        low_memory=False,
    )
    log.info("  %s linhas lidas", f"{len(df):,}".replace(",", "."))

    df = df[df["TP_DOCUMENTO"] == "J"].copy()
    df["cnpj_proposta"] = df["NR_DOCUMENTO"].map(limpar_cnpj)

    saida = pd.DataFrame(
        {
            "cd_orgao": df["CD_ORGAO"].map(normalizar_texto),
            "nr_licitacao": df["NR_LICITACAO"].map(normalizar_texto),
            "ano_licitacao": df["ANO_LICITACAO"].map(normalizar_texto),
            "cd_tipo_modalidade": df["CD_TIPO_MODALIDADE"].map(normalizar_texto),
            "nr_lote": df["NR_LOTE"].map(normalizar_texto),
            "nr_item": df["NR_ITEM"].map(normalizar_texto),
            "cnpj_proposta": df["cnpj_proposta"],
            "valor_unitario": df["VL_UNITARIO"].map(limpar_valor),
            "valor_total_item": df["VL_TOTAL_ITEM"].map(limpar_valor),
            "percentual_desconto": df["PC_DESCONTO"].map(limpar_valor),
            "percentual_bdi": df["PC_BDI"].map(limpar_valor),
            "valor_nota_tecnica": df["VL_NOTA_TECNICA"].map(limpar_valor),
            "data_homologacao": df["DT_HOMOLOGACAO"].map(padronizar_data),
            "resultado_proposta": df["TP_RESULTADO_PROPOSTA"].map(normalizar_texto),
            "resultado_habilitacao": df["TP_RESULTADO_HABILITACAO"].map(normalizar_texto),
        }
    )

    antes = len(saida)
    saida = saida[saida["cnpj_proposta"].notna()].copy()
    log.info("  %s linhas descartadas por CNPJ inválido", antes - len(saida))

    chave = [
        "cd_orgao",
        "nr_licitacao",
        "ano_licitacao",
        "cd_tipo_modalidade",
        "nr_lote",
        "nr_item",
        "cnpj_proposta",
    ]
    antes = len(saida)
    saida = saida.drop_duplicates(subset=chave, keep="first")
    if antes != len(saida):
        log.info("  %s duplicatas removidas pela chave composta", antes - len(saida))

    log.info("  %s linhas no resultado final", f"{len(saida):,}".replace(",", "."))
    return saida
