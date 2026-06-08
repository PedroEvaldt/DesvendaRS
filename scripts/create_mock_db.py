"""Create a tiny mock DuckDB database for testing the Streamlit UI.

This script uses the same schema and view definitions as `etl.build_db`, but
fills them with hand-crafted rows. It is meant only for local app development
while the real `data/raw/` files or generated `db/dados.duckdb` are unavailable.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from etl.build_db import VIEWS, _criar_tabela


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        type=Path,
        default=config.DB_PATH,
        help="Output DuckDB path. Defaults to db/dados.duckdb.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the target database if it already exists.",
    )
    args = parser.parse_args()

    if args.path.exists() and not args.force:
        raise SystemExit(
            f"{args.path} already exists. Use --force only if you want to replace it."
        )

    args.path.parent.mkdir(parents=True, exist_ok=True)
    if args.path.exists():
        args.path.unlink()

    con = duckdb.connect(str(args.path))
    try:
        for table, df in _mock_tables().items():
            _criar_tabela(con, table, df)
        for name, sql in VIEWS.items():
            con.execute(f"DROP VIEW IF EXISTS {name}")
            con.execute(sql)
    finally:
        con.close()

    print(f"Mock database created at {args.path}")


def _mock_tables() -> dict[str, pd.DataFrame]:
    return {
        "contratos": _contratos(),
        "empresas": _empresas(),
        "socios": _socios(),
        "sancoes": _sancoes(),
        "itens": _itens(),
        "propostas": _propostas(),
        "propostas_itens": _propostas_itens(),
        "eventos_licitacao": _eventos(),
    }


def _contratos() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cnpj_fornecedor": "12345678000195",
                "razao_social": "MEDSUL SUPRIMENTOS HOSPITALARES LTDA",
                "orgao": "PM DE PORTO ALEGRE",
                "municipio": "PORTO ALEGRE",
                "modalidade": "PRE",
                "objeto": "Aquisicao emergencial de mascaras e aventais",
                "valor_contrato": 850000.00,
                "data_contrato": date(2026, 3, 12),
                "numero_contrato": "2026-001",
                "qtd_participantes": 1,
                "flag_covid": True,
            },
            {
                "cnpj_fornecedor": "22345678000195",
                "razao_social": "ALFA OBRAS E SERVICOS LTDA",
                "orgao": "PM DE CANOAS",
                "municipio": "CANOAS",
                "modalidade": "DSP",
                "objeto": "Manutencao predial em escolas municipais",
                "valor_contrato": 420000.00,
                "data_contrato": date(2026, 2, 18),
                "numero_contrato": "2026-014",
                "qtd_participantes": 2,
                "flag_covid": False,
            },
            {
                "cnpj_fornecedor": "32345678000195",
                "razao_social": "BETA TECNOLOGIA PUBLICA SA",
                "orgao": "PM DE PELOTAS",
                "municipio": "PELOTAS",
                "modalidade": "PRE",
                "objeto": "Licenciamento de software de atendimento ao cidadao",
                "valor_contrato": 290000.00,
                "data_contrato": date(2026, 1, 27),
                "numero_contrato": "2026-022",
                "qtd_participantes": 4,
                "flag_covid": False,
            },
            {
                "cnpj_fornecedor": "42345678000195",
                "razao_social": "GAMA ALIMENTOS LTDA",
                "orgao": "PM DE SANTA MARIA",
                "municipio": "SANTA MARIA",
                "modalidade": "PRE",
                "objeto": "Compra de cestas basicas para assistencia social",
                "valor_contrato": 175000.00,
                "data_contrato": date(2026, 4, 5),
                "numero_contrato": "2026-033",
                "qtd_participantes": 6,
                "flag_covid": False,
            },
        ]
    )


def _empresas() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cnpj": "12345678000195",
                "razao_social": "MEDSUL SUPRIMENTOS HOSPITALARES LTDA",
                "data_abertura": date(2025, 12, 20),
                "cnae": "4644301",
                "capital_social": 5000.00,
                "situacao_cadastral": "8",
                "porte": "ME",
                "endereco": "RUA DOS ANDRADAS 1000",
                "municipio": "PORTO ALEGRE",
            },
            {
                "cnpj": "22345678000195",
                "razao_social": "ALFA OBRAS E SERVICOS LTDA",
                "data_abertura": date(2021, 6, 10),
                "cnae": "4120400",
                "capital_social": 20000.00,
                "situacao_cadastral": "2",
                "porte": "EPP",
                "endereco": "AVENIDA GUILHERME SCHELL 200",
                "municipio": "CANOAS",
            },
            {
                "cnpj": "32345678000195",
                "razao_social": "BETA TECNOLOGIA PUBLICA SA",
                "data_abertura": date(2018, 9, 1),
                "cnae": "6204000",
                "capital_social": 900000.00,
                "situacao_cadastral": "2",
                "porte": "DEMAIS",
                "endereco": "RUA XV DE NOVEMBRO 50",
                "municipio": "PELOTAS",
            },
            {
                "cnpj": "42345678000195",
                "razao_social": "GAMA ALIMENTOS LTDA",
                "data_abertura": date(2019, 3, 22),
                "cnae": "4639701",
                "capital_social": 120000.00,
                "situacao_cadastral": "2",
                "porte": "EPP",
                "endereco": "RUA VENANCIO AIRES 123",
                "municipio": "SANTA MARIA",
            },
        ]
    )


def _socios() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cnpj": "12345678000195",
                "nome_socio": "ANA SILVA",
                "doc_socio": "***123456**",
                "tipo_socio": "Pessoa fisica",
                "qualificacao": "Socio administrador",
                "data_entrada": date(2025, 12, 21),
            },
            {
                "cnpj": "22345678000195",
                "nome_socio": "CARLOS LIMA",
                "doc_socio": "***223456**",
                "tipo_socio": "Pessoa fisica",
                "qualificacao": "Socio administrador",
                "data_entrada": date(2021, 6, 10),
            },
            {
                "cnpj": "32345678000195",
                "nome_socio": "RENATA COSTA",
                "doc_socio": "***323456**",
                "tipo_socio": "Pessoa fisica",
                "qualificacao": "Diretor",
                "data_entrada": date(2018, 9, 1),
            },
        ]
    )


def _sancoes() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cnpj": "12345678000195",
                "tipo_sancao": "Impedimento de licitar",
                "orgao_sancionador": "Controladoria-Geral da Uniao",
                "data_inicio": date(2025, 11, 1),
                "data_fim": date(2026, 11, 1),
                "fonte": "CEIS",
            },
            {
                "cnpj": "22345678000195",
                "tipo_sancao": "Multa administrativa",
                "orgao_sancionador": "PGE-RS",
                "data_inicio": date(2023, 5, 15),
                "data_fim": date(2023, 12, 31),
                "fonte": "CFIL",
            },
        ]
    )


def _itens() -> pd.DataFrame:
    rows = []
    for idx, value in enumerate([9.8, 10.1, 10.4, 10.2, 9.9, 10.5, 10.0, 9.7, 10.3, 10.1], start=1):
        rows.append(_item_row("001", "100", "2026", "PRE", "1", str(idx), "12345678000195", value, False))
    rows.append(_item_row("001", "100", "2026", "PRE", "1", "99", "12345678000195", 62.0, True))
    rows.append(_item_row("002", "200", "2026", "DSP", "1", "1", "22345678000195", 150.0, False, "SERVICO DE MANUTENCAO PREDIAL", "UN"))
    return pd.DataFrame(rows)


def _item_row(
    cd_orgao: str,
    nr_licitacao: str,
    ano: str,
    modalidade: str,
    lote: str,
    item: str,
    cnpj: str,
    unitario: float,
    covid: bool,
    descricao: str = "MASCARA CIRURGICA DESCARTAVEL",
    unidade: str = "UN",
) -> dict:
    return {
        "cd_orgao": cd_orgao,
        "nr_licitacao": nr_licitacao,
        "ano_licitacao": ano,
        "cd_tipo_modalidade": modalidade,
        "nr_lote": lote,
        "nr_item": item,
        "cnpj_fornecedor": cnpj,
        "descricao": descricao,
        "descricao_normalizada": descricao.lower(),
        "quantidade": 100.0,
        "unidade": unidade,
        "valor_unitario_estimado": 12.0,
        "valor_unitario_homologado": unitario,
        "valor_total_homologado": unitario * 100,
        "flag_covid": covid,
    }


def _propostas() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _proposta("001", "100", "2026", "PRE", "12345678000195", "C", 850000.00),
            _proposta("002", "200", "2026", "DSP", "22345678000195", "C", 420000.00),
            _proposta("003", "300", "2026", "PRE", "32345678000195", "C", 100000.00),
            _proposta("003", "300", "2026", "PRE", "52345678000195", "C", 250000.00),
            _proposta("003", "300", "2026", "PRE", "62345678000195", "C", 260000.00),
            _proposta("004", "400", "2026", "PRE", "42345678000195", "C", 175000.00),
            _proposta("004", "400", "2026", "PRE", "72345678000195", "D", 150000.00),
        ]
    )


def _proposta(
    cd_orgao: str,
    nr_licitacao: str,
    ano: str,
    modalidade: str,
    cnpj: str,
    resultado: str,
    valor: float,
) -> dict:
    return {
        "cd_orgao": cd_orgao,
        "nr_licitacao": nr_licitacao,
        "ano_licitacao": ano,
        "cd_tipo_modalidade": modalidade,
        "cnpj_proposta": cnpj,
        "data_proposta": date(2026, 1, 10),
        "resultado_proposta": resultado,
        "valor_total_proposta": valor,
        "percentual_desconto": 0.0,
        "valor_nota_tecnica": None,
        "data_homologacao": date(2026, 1, 25),
    }


def _propostas_itens() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cd_orgao": "003",
                "nr_licitacao": "300",
                "ano_licitacao": "2026",
                "cd_tipo_modalidade": "PRE",
                "nr_lote": "1",
                "nr_item": "1",
                "cnpj_proposta": "32345678000195",
                "valor_unitario": 100.0,
                "valor_total_item": 100000.0,
                "percentual_desconto": 0.0,
                "percentual_bdi": None,
                "valor_nota_tecnica": None,
                "data_homologacao": date(2026, 1, 25),
                "resultado_proposta": "C",
                "resultado_habilitacao": "H",
            }
        ]
    )


def _eventos() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _evento("003", "300", "2026", "PRE", "1", "PUB", date(2026, 1, 5)),
            _evento("003", "300", "2026", "PRE", "2", "AED", date(2026, 2, 20)),
            _evento("004", "400", "2026", "PRE", "1", "PUB", date(2026, 3, 1)),
            _evento("004", "400", "2026", "PRE", "2", "REE", date(2026, 3, 20)),
        ]
    )


def _evento(
    cd_orgao: str,
    nr_licitacao: str,
    ano: str,
    modalidade: str,
    sq_evento: str,
    tipo: str,
    data_evento: date,
) -> dict:
    return {
        "cd_orgao": cd_orgao,
        "nr_licitacao": nr_licitacao,
        "ano_licitacao": ano,
        "cd_tipo_modalidade": modalidade,
        "sq_evento": sq_evento,
        "cd_tipo_fase": "1",
        "cd_tipo_evento": tipo,
        "data_evento": data_evento,
        "tipo_veiculo_publicacao": "DOE",
        "descricao_publicacao": "Publicacao de evento simulado para teste de interface",
        "cnpj_autor": None,
        "data_julgamento": None,
        "tipo_resultado": None,
        "nr_lote": None,
        "nr_item": None,
    }


if __name__ == "__main__":
    main()
