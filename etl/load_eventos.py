"""Loader da tabela `eventos_licitacao` a partir de evento_lic.csv.

Granularidade: 1 linha por evento na linha do tempo de uma licitação.
Cada licitação tem N eventos (publicação, abertura, alteração, julgamento,
homologação, etc.).

Base para análise de:
- Alteração de edital depois da data de abertura.
- Tempo entre publicação e abertura (cumprimento de prazo legal mínimo).
- Sequência confusa de eventos (sinal de retrabalho).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

import config
from etl.normalize import (
    limpar_cnpj,
    normalizar_texto,
    padronizar_data,
)

log = logging.getLogger(__name__)


def load_eventos(path: Path = config.CSV_EVENTO_LIC) -> pd.DataFrame:
    log.info("Lendo %s", path.name)
    df = pd.read_csv(
        path,
        dtype=str,
        encoding="utf-8-sig",
        low_memory=False,
    )
    log.info("  %s linhas lidas", f"{len(df):,}".replace(",", "."))

    # Autor pode ser PJ ou PF; só guardamos CNPJ quando for PJ (LGPD).
    cnpj_autor = df.apply(
        lambda r: r["NR_DOCUMENTO_AUTOR"] if r["TP_DOCUMENTO_AUTOR"] == "J" else None,
        axis=1,
    )

    saida = pd.DataFrame(
        {
            "cd_orgao": df["CD_ORGAO"].map(normalizar_texto),
            "nr_licitacao": df["NR_LICITACAO"].map(normalizar_texto),
            "ano_licitacao": df["ANO_LICITACAO"].map(normalizar_texto),
            "cd_tipo_modalidade": df["CD_TIPO_MODALIDADE"].map(normalizar_texto),
            "sq_evento": df["SQ_EVENTO"].map(normalizar_texto),
            "cd_tipo_fase": df["CD_TIPO_FASE"].map(normalizar_texto),
            "cd_tipo_evento": df["CD_TIPO_EVENTO"].map(normalizar_texto),
            "data_evento": df["DT_EVENTO"].map(padronizar_data),
            "tipo_veiculo_publicacao": df["TP_VEICULO_PUBLICACAO"].map(normalizar_texto),
            "descricao_publicacao": df["DS_PUBLICACAO"].map(normalizar_texto),
            "cnpj_autor": cnpj_autor.map(limpar_cnpj),
            "data_julgamento": df["DT_JULGAMENTO"].map(padronizar_data),
            "tipo_resultado": df["TP_RESULTADO"].map(normalizar_texto),
            "nr_lote": df["NR_LOTE"].map(normalizar_texto),
            "nr_item": df["NR_ITEM"].map(normalizar_texto),
        }
    )

    chave = [
        "cd_orgao",
        "nr_licitacao",
        "ano_licitacao",
        "cd_tipo_modalidade",
        "sq_evento",
    ]
    antes = len(saida)
    saida = saida.drop_duplicates(subset=chave, keep="first")
    if antes != len(saida):
        log.info("  %s duplicatas removidas pela chave composta", antes - len(saida))

    log.info("  %s linhas no resultado final", f"{len(saida):,}".replace(",", "."))
    return saida
