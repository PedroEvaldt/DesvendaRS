"""Loader da tabela `propostas` a partir de proposta.csv (LicitaCon).

Granularidade: 1 linha por (licitação × fornecedor que apresentou proposta).
A chave composta da licitação é a mesma das demais tabelas LicitaCon:
(CD_ORGAO, NR_LICITACAO, ANO_LICITACAO, CD_TIPO_MODALIDADE).

Base para análise de:
- Cover bidding (proposta perdedora artificialmente alta).
- Licitações com proposta única classificada.
- Rotação de cartel (mesmas empresas alternando vitórias entre licitações).

Só pessoa jurídica é mantida (filtro TP_DOCUMENTO='J').
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


def load_propostas(path: Path = config.CSV_PROPOSTA) -> pd.DataFrame:
    log.info("Lendo %s", path.name)
    df = pd.read_csv(
        path,
        dtype=str,
        encoding="utf-8-sig",
        low_memory=False,
    )
    log.info("  %s linhas lidas", f"{len(df):,}".replace(",", "."))

    # Só PJ; CPF de pessoa física é descartado
    df = df[df["TP_DOCUMENTO"] == "J"].copy()
    df["cnpj_proposta"] = df["NR_DOCUMENTO"].map(limpar_cnpj)

    saida = pd.DataFrame(
        {
            "cd_orgao": df["CD_ORGAO"].map(normalizar_texto),
            "nr_licitacao": df["NR_LICITACAO"].map(normalizar_texto),
            "ano_licitacao": df["ANO_LICITACAO"].map(normalizar_texto),
            "cd_tipo_modalidade": df["CD_TIPO_MODALIDADE"].map(normalizar_texto),
            "cnpj_proposta": df["cnpj_proposta"],
            "data_proposta": df["DT_PROPOSTA"].map(padronizar_data),
            "resultado_proposta": df["TP_RESULTADO_PROPOSTA"].map(normalizar_texto),
            "valor_total_proposta": df["VL_TOTAL_PROPOSTA"].map(limpar_valor),
            "percentual_desconto": df["PC_DESCONTO"].map(limpar_valor),
            "valor_nota_tecnica": df["VL_NOTA_TECNICA"].map(limpar_valor),
            "data_homologacao": df["DT_HOMOLOGACAO"].map(padronizar_data),
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
        "cnpj_proposta",
    ]
    antes = len(saida)
    saida = saida.drop_duplicates(subset=chave, keep="first")
    if antes != len(saida):
        log.info("  %s duplicatas removidas pela chave composta", antes - len(saida))

    log.info("  %s linhas no resultado final", f"{len(saida):,}".replace(",", "."))
    return saida
