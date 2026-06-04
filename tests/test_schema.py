"""Valida que db/dados.duckdb está no esquema da Seção 6 do CLAUDE.md e que
CNPJs estão limpos (14 dígitos, sem pontuação) em todas as tabelas-chave.
"""
from __future__ import annotations

import pytest

ESQUEMA_ESPERADO = {
    "contratos": {
        "cnpj_fornecedor": "VARCHAR",
        "razao_social": "VARCHAR",
        "orgao": "VARCHAR",
        "municipio": "VARCHAR",
        "modalidade": "VARCHAR",
        "objeto": "VARCHAR",
        "valor_contrato": "DECIMAL(18,2)",
        "data_contrato": "DATE",
        "numero_contrato": "VARCHAR",
        "qtd_participantes": "INTEGER",
        "flag_covid": "BOOLEAN",
    },
    "empresas": {
        "cnpj": "VARCHAR",
        "razao_social": "VARCHAR",
        "data_abertura": "DATE",
        "cnae": "VARCHAR",
        "capital_social": "DECIMAL(18,2)",
        "situacao_cadastral": "VARCHAR",
        "porte": "VARCHAR",
        "endereco": "VARCHAR",
        "municipio": "VARCHAR",
    },
    "socios": {
        "cnpj": "VARCHAR",
        "nome_socio": "VARCHAR",
        "doc_socio": "VARCHAR",
        "tipo_socio": "VARCHAR",
        "qualificacao": "VARCHAR",
        "data_entrada": "DATE",
    },
    "sancoes": {
        "cnpj": "VARCHAR",
        "tipo_sancao": "VARCHAR",
        "orgao_sancionador": "VARCHAR",
        "data_inicio": "DATE",
        "data_fim": "DATE",
        "fonte": "VARCHAR",
    },
    "itens": {
        "cd_orgao": "VARCHAR",
        "nr_licitacao": "VARCHAR",
        "ano_licitacao": "VARCHAR",
        "cd_tipo_modalidade": "VARCHAR",
        "nr_lote": "VARCHAR",
        "nr_item": "VARCHAR",
        "cnpj_fornecedor": "VARCHAR",
        "descricao": "VARCHAR",
        "descricao_normalizada": "VARCHAR",
        "quantidade": "DECIMAL(18,4)",
        "unidade": "VARCHAR",
        "valor_unitario_estimado": "DECIMAL(18,4)",
        "valor_unitario_homologado": "DECIMAL(18,4)",
        "valor_total_homologado": "DECIMAL(18,2)",
        "flag_covid": "BOOLEAN",
    },
    "propostas": {
        "cd_orgao": "VARCHAR",
        "nr_licitacao": "VARCHAR",
        "ano_licitacao": "VARCHAR",
        "cd_tipo_modalidade": "VARCHAR",
        "cnpj_proposta": "VARCHAR",
        "data_proposta": "DATE",
        "resultado_proposta": "VARCHAR",
        "valor_total_proposta": "DECIMAL(18,2)",
        "percentual_desconto": "DECIMAL(8,4)",
        "valor_nota_tecnica": "DECIMAL(18,4)",
        "data_homologacao": "DATE",
    },
    "propostas_itens": {
        "cd_orgao": "VARCHAR",
        "nr_licitacao": "VARCHAR",
        "ano_licitacao": "VARCHAR",
        "cd_tipo_modalidade": "VARCHAR",
        "nr_lote": "VARCHAR",
        "nr_item": "VARCHAR",
        "cnpj_proposta": "VARCHAR",
        "valor_unitario": "DECIMAL(18,4)",
        "valor_total_item": "DECIMAL(18,2)",
        "percentual_desconto": "DECIMAL(8,4)",
        "percentual_bdi": "DECIMAL(8,4)",
        "valor_nota_tecnica": "DECIMAL(18,4)",
        "data_homologacao": "DATE",
        "resultado_proposta": "VARCHAR",
        "resultado_habilitacao": "VARCHAR",
    },
    "eventos_licitacao": {
        "cd_orgao": "VARCHAR",
        "nr_licitacao": "VARCHAR",
        "ano_licitacao": "VARCHAR",
        "cd_tipo_modalidade": "VARCHAR",
        "sq_evento": "VARCHAR",
        "cd_tipo_fase": "VARCHAR",
        "cd_tipo_evento": "VARCHAR",
        "data_evento": "DATE",
        "tipo_veiculo_publicacao": "VARCHAR",
        "descricao_publicacao": "VARCHAR",
        "cnpj_autor": "VARCHAR",
        "data_julgamento": "DATE",
        "tipo_resultado": "VARCHAR",
        "nr_lote": "VARCHAR",
        "nr_item": "VARCHAR",
    },
}


@pytest.mark.parametrize("tabela,colunas_esperadas", ESQUEMA_ESPERADO.items())
def test_colunas_e_tipos(con, tabela, colunas_esperadas):
    info = con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [tabela],
    ).fetchall()
    obtido = {nome: tipo for nome, tipo in info}
    assert obtido == colunas_esperadas, (
        f"Tabela {tabela}: esquema diverge.\n"
        f"  esperado: {colunas_esperadas}\n"
        f"  obtido:   {obtido}"
    )


@pytest.mark.parametrize(
    "tabela,coluna",
    [
        ("contratos", "cnpj_fornecedor"),
        ("empresas", "cnpj"),
        ("socios", "cnpj"),
        ("sancoes", "cnpj"),
        ("itens", "cnpj_fornecedor"),
        ("propostas", "cnpj_proposta"),
        ("propostas_itens", "cnpj_proposta"),
        ("eventos_licitacao", "cnpj_autor"),
    ],
)
def test_cnpj_tem_14_digitos_sem_pontuacao(con, tabela, coluna):
    """CNPJs não-nulos precisam ter exatamente 14 caracteres, todos dígitos."""
    invalidos = con.execute(
        f"SELECT COUNT(*) FROM {tabela} "
        f"WHERE {coluna} IS NOT NULL AND "
        f"(LENGTH({coluna}) <> 14 OR {coluna} !~ '^[0-9]+$')"
    ).fetchone()[0]
    assert invalidos == 0, (
        f"{tabela}.{coluna}: {invalidos} CNPJs malformados (≠14 dígitos ou com lixo)"
    )


def test_sancoes_fonte_apenas_valida(con):
    fontes = {r[0] for r in con.execute(
        "SELECT DISTINCT fonte FROM sancoes WHERE fonte IS NOT NULL"
    ).fetchall()}
    assert fontes == {"CEIS", "CNEP", "CFIL"}, (
        f"sancoes.fonte deveria conter só CEIS/CNEP/CFIL, achou {fontes}"
    )
