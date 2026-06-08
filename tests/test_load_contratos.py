"""Testes do loader de contratos a partir dos CSVs LicitaCon."""
from __future__ import annotations

import pandas as pd

from etl.load_contratos import load_contratos


def test_load_contratos_usa_fornecedor_como_fallback_de_vencedor(tmp_path):
    licitacao = tmp_path / "licitacao.csv"
    licitante = tmp_path / "licitante.csv"
    pessoas = tmp_path / "pessoas.csv"

    pd.DataFrame(
        [
            {
                "CD_ORGAO": "001",
                "NR_LICITACAO": "100",
                "ANO_LICITACAO": "2026",
                "CD_TIPO_MODALIDADE": "PRE",
                "NM_ORGAO": "PM DE PELOTAS",
                "DS_OBJETO": "Servico de tecnologia",
                "VL_LICITACAO": "1000,00",
                "VL_HOMOLOGADO": "900,00",
                "DT_ABERTURA": "2026-01-10",
                "DT_HOMOLOGACAO": "2026-01-20",
                "NR_PROCESSO": "PROC-100",
                "BL_COVID19": "N",
                "TP_DOCUMENTO_FORNECEDOR": "J",
                "NR_DOCUMENTO_FORNECEDOR": "12345678000195",
                "TP_DOCUMENTO_VENCEDOR": None,
                "NR_DOCUMENTO_VENCEDOR": None,
            }
        ]
    ).to_csv(licitacao, index=False)
    pd.DataFrame(
        [
            {
                "CD_ORGAO": "001",
                "NR_LICITACAO": "100",
                "ANO_LICITACAO": "2026",
                "CD_TIPO_MODALIDADE": "PRE",
                "TP_DOCUMENTO": "J",
                "NR_DOCUMENTO": "12345678000195",
            }
        ]
    ).to_csv(licitante, index=False)
    pd.DataFrame(
        [
            {
                "TP_DOCUMENTO": "J",
                "NR_DOCUMENTO": "12345678000195",
                "TP_PESSOA": "J",
                "NM_PESSOA": "Beta Tecnologia Publica SA",
            }
        ]
    ).to_csv(pessoas, index=False)

    df = load_contratos(licitacao=licitacao, pessoas=pessoas, licitante=licitante)

    assert df.iloc[0]["cnpj_vencedor"] == "12345678000195"
    assert df.iloc[0]["razao_social"] == "BETA TECNOLOGIA PUBLICA SA"


def test_load_contratos_prefere_vencedor_quando_informado(tmp_path):
    licitacao = tmp_path / "licitacao.csv"
    licitante = tmp_path / "licitante.csv"
    pessoas = tmp_path / "pessoas.csv"

    pd.DataFrame(
        [
            {
                "CD_ORGAO": "001",
                "NR_LICITACAO": "100",
                "ANO_LICITACAO": "2026",
                "CD_TIPO_MODALIDADE": "PRE",
                "NM_ORGAO": "PM DE PELOTAS",
                "DS_OBJETO": "Servico de tecnologia",
                "VL_LICITACAO": "1000,00",
                "VL_HOMOLOGADO": "900,00",
                "DT_ABERTURA": "2026-01-10",
                "DT_HOMOLOGACAO": "2026-01-20",
                "NR_PROCESSO": "PROC-100",
                "BL_COVID19": "N",
                "TP_DOCUMENTO_FORNECEDOR": "J",
                "NR_DOCUMENTO_FORNECEDOR": "12345678000195",
                "TP_DOCUMENTO_VENCEDOR": "J",
                "NR_DOCUMENTO_VENCEDOR": "22345678000195",
            }
        ]
    ).to_csv(licitacao, index=False)
    pd.DataFrame(
        [
            {
                "CD_ORGAO": "001",
                "NR_LICITACAO": "100",
                "ANO_LICITACAO": "2026",
                "CD_TIPO_MODALIDADE": "PRE",
                "TP_DOCUMENTO": "J",
                "NR_DOCUMENTO": "12345678000195",
            }
        ]
    ).to_csv(licitante, index=False)
    pd.DataFrame(
        [
            {
                "TP_DOCUMENTO": "J",
                "NR_DOCUMENTO": "12345678000195",
                "TP_PESSOA": "J",
                "NM_PESSOA": "Beta Tecnologia Publica SA",
            }
        ]
    ).to_csv(pessoas, index=False)

    df = load_contratos(licitacao=licitacao, pessoas=pessoas, licitante=licitante)

    assert df.iloc[0]["cnpj_vencedor"] == "22345678000195"
