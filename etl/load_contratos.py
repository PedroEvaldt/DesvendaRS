"""Loader da tabela `contratos` a partir das tabelas LicitaCon.

Estratégia de granularidade:
  * 1 linha por (licitação × fornecedor participante).
  * `qtd_participantes` é calculado por licitação a partir de `licitante.csv`.
  * Razão social vem de `pessoas.csv` quando disponível; cai para o nome embutido
    na própria `licitacao.csv` se o cruzamento por CNPJ falhar.

Os arquivos do LicitaCon não têm `id_licitacao` único; a chave de ligação é a tupla
``(CD_ORGAO, NR_LICITACAO, ANO_LICITACAO, CD_TIPO_MODALIDADE)``.

`DT_HOMOLOGACAO` é nulo em ~63% das linhas (licitações em andamento) — usamos
fallback para `DT_ABERTURA`. Idem `VL_HOMOLOGADO` → `VL_LICITACAO`.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

import config
from etl.normalize import limpar_cnpj, limpar_valor, normalizar_texto, padronizar_data

# Padrão dos órgãos municipais no LicitaCon: "PM DE <CIDADE>" (Prefeitura)
# ou "CM DE <CIDADE>" (Câmara). Cobre ~89% das linhas; órgãos estaduais e
# consórcios ficam sem município (NULL).
_RE_MUNICIPIO = re.compile(r"^(?:PM|CM)\s+DE\s+(.+?)\s*$", re.IGNORECASE)

log = logging.getLogger(__name__)

CHAVE = ["CD_ORGAO", "NR_LICITACAO", "ANO_LICITACAO", "CD_TIPO_MODALIDADE"]


def _carregar_pessoas_pj(path: Path) -> pd.DataFrame:
    """Constrói mapa CNPJ → razão social a partir de pessoas.csv (filtrando PJ)."""
    log.info("Lendo %s (apenas PJ)", path.name)
    df = pd.read_csv(
        path,
        dtype=str,
        usecols=["TP_DOCUMENTO", "NR_DOCUMENTO", "TP_PESSOA", "NM_PESSOA"],
        encoding="utf-8-sig",
        low_memory=False,
    )
    df = df[df["TP_DOCUMENTO"] == "J"].copy()
    df["cnpj"] = df["NR_DOCUMENTO"].map(limpar_cnpj)
    df = df[df["cnpj"].notna() & df["NM_PESSOA"].notna()]
    df["razao_social"] = df["NM_PESSOA"].map(lambda v: normalizar_texto(v, upper=True))
    mapa = df[["cnpj", "razao_social"]].drop_duplicates(subset="cnpj")
    log.info("  %s CNPJs com razão social", f"{len(mapa):,}".replace(",", "."))
    return mapa


def _carregar_licitantes(path: Path) -> pd.DataFrame:
    """Lê licitante.csv. Cada linha = um licitante (PJ no par primário, PF no .1).

    Devolve DataFrame com chave da licitação + CNPJ do fornecedor + qtd_participantes.
    """
    log.info("Lendo %s", path.name)
    df = pd.read_csv(
        path,
        dtype=str,
        encoding="utf-8-sig",
        low_memory=False,
    )
    df = df[df["TP_DOCUMENTO"] == "J"].copy()
    df["cnpj_fornecedor"] = df["NR_DOCUMENTO"].map(limpar_cnpj)
    df = df[df["cnpj_fornecedor"].notna()]

    qtd = (
        df.groupby(CHAVE, dropna=False)["cnpj_fornecedor"]
        .nunique()
        .reset_index(name="qtd_participantes")
    )

    licitantes = df[CHAVE + ["cnpj_fornecedor"]].drop_duplicates()
    licitantes = licitantes.merge(qtd, on=CHAVE, how="left")
    log.info(
        "  %s linhas licitação×fornecedor", f"{len(licitantes):,}".replace(",", ".")
    )
    return licitantes


def _carregar_licitacoes(path: Path) -> pd.DataFrame:
    """Lê licitacao.csv selecionando só as colunas que viram contrato."""
    log.info("Lendo %s", path.name)
    cols = CHAVE + [
        "NM_ORGAO",
        "DS_OBJETO",
        "VL_LICITACAO",
        "VL_HOMOLOGADO",
        "DT_ABERTURA",
        "DT_HOMOLOGACAO",
        "NR_PROCESSO",
        "BL_COVID19",
        "TP_DOCUMENTO_FORNECEDOR",
        "NR_DOCUMENTO_FORNECEDOR",
        "TP_DOCUMENTO_VENCEDOR",
        "NR_DOCUMENTO_VENCEDOR",
    ]
    df = pd.read_csv(
        path,
        dtype=str,
        usecols=cols,
        encoding="utf-8-sig",
        low_memory=False,
    )
    log.info("  %s licitações", f"{len(df):,}".replace(",", "."))
    return df


def load_contratos(
    licitacao: Path = config.CSV_LICITACAO,
    pessoas: Path = config.CSV_PESSOAS,
    licitante: Path = config.CSV_LICITANTE,
) -> pd.DataFrame:
    """Junta licitação + licitantes + pessoas e devolve a tabela `contratos`.

    Retorna 1 linha por licitação×fornecedor participante. Para licitações sem
    nenhum fornecedor registrado em `licitante.csv`, mantém a linha base com
    `cnpj_fornecedor` nulo (visibilidade do que ainda não foi homologado).
    """
    lic = _carregar_licitacoes(licitacao)
    licitantes = _carregar_licitantes(licitante)
    mapa_pessoas = _carregar_pessoas_pj(pessoas)

    log.info("Combinando licitações e licitantes")
    df = lic.merge(licitantes, on=CHAVE, how="left")

    log.info("Casando razão social via pessoas.csv")
    df = df.merge(mapa_pessoas, left_on="cnpj_fornecedor", right_on="cnpj", how="left")
    df = df.drop(columns=["cnpj"])

    # Chave composta da licitação — normalizada IGUAL a load_propostas.py
    # (normalizar_texto sem upper) para que o JOIN contratos↔propostas case.
    df["cd_orgao"] = df["CD_ORGAO"].map(normalizar_texto)
    df["nr_licitacao"] = df["NR_LICITACAO"].map(normalizar_texto)
    df["ano_licitacao"] = df["ANO_LICITACAO"].map(normalizar_texto)
    df["cd_tipo_modalidade"] = df["CD_TIPO_MODALIDADE"].map(normalizar_texto)

    # Vencedor oficial homologado da licitação (só quando é pessoa jurídica)
    df["cnpj_vencedor"] = df.apply(
        lambda r: limpar_cnpj(r["NR_DOCUMENTO_VENCEDOR"])
        if r["TP_DOCUMENTO_VENCEDOR"] == "J"
        else None,
        axis=1,
    )

    # Normalizações finais
    df["modalidade"] = df["CD_TIPO_MODALIDADE"].map(normalizar_texto)
    df["orgao"] = df["NM_ORGAO"].map(normalizar_texto)
    df["municipio"] = df["orgao"].map(_extrair_municipio)
    df["objeto"] = df["DS_OBJETO"].map(normalizar_texto)
    df["valor_contrato"] = df["VL_HOMOLOGADO"].fillna(df["VL_LICITACAO"]).map(limpar_valor)
    df["data_contrato"] = df["DT_HOMOLOGACAO"].fillna(df["DT_ABERTURA"]).map(padronizar_data)
    df["numero_contrato"] = df["NR_PROCESSO"].map(normalizar_texto)
    df["flag_covid"] = df["BL_COVID19"].map(_para_bool)

    saida = df[
        [
            "cnpj_fornecedor",
            "razao_social",
            "orgao",
            "municipio",
            "modalidade",
            "objeto",
            "valor_contrato",
            "data_contrato",
            "numero_contrato",
            "qtd_participantes",
            "flag_covid",
            "cd_orgao",
            "nr_licitacao",
            "ano_licitacao",
            "cd_tipo_modalidade",
            "cnpj_vencedor",
        ]
    ]
    log.info(
        "  %s linhas no resultado final", f"{len(saida):,}".replace(",", ".")
    )
    return saida


def _extrair_municipio(orgao: object) -> str | None:
    """Extrai nome do município de NM_ORGAO quando o padrão é PM/CM DE <cidade>."""
    if orgao is None or (isinstance(orgao, float) and orgao != orgao):
        return None
    m = _RE_MUNICIPIO.match(str(orgao))
    return m.group(1).strip() if m else None


def _para_bool(valor: object) -> bool | None:
    """Converte 'S'/'N'/'true'/'false'/'1'/'0' para bool. Outros valores → None."""
    if valor is None:
        return None
    if isinstance(valor, float) and valor != valor:
        return None
    s = str(valor).strip().upper()
    if s in {"S", "SIM", "TRUE", "T", "1", "Y", "YES"}:
        return True
    if s in {"N", "NAO", "NÃO", "FALSE", "F", "0", "N/A"}:
        return False
    return None
