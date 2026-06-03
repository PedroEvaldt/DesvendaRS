"""Sanity check de cruzamento por CNPJ entre as 4 tabelas.

Se nenhum CNPJ casar entre `contratos` e as outras fontes, o pipeline está
quebrado — quase certamente erro na normalização do CNPJ.
"""
from __future__ import annotations


def test_contratos_casam_com_empresas(con):
    n = con.execute(
        "SELECT COUNT(DISTINCT c.cnpj_fornecedor) "
        "FROM contratos c JOIN empresas e ON c.cnpj_fornecedor = e.cnpj"
    ).fetchone()[0]
    assert n > 0, (
        "Nenhum fornecedor de `contratos` foi achado em `empresas`. "
        "Provável bug em limpar_cnpj ou na origem do CNPJ no LicitaCon."
    )


def test_contratos_casam_com_sancoes(con):
    n = con.execute(
        "SELECT COUNT(DISTINCT c.cnpj_fornecedor) "
        "FROM contratos c JOIN sancoes s ON c.cnpj_fornecedor = s.cnpj"
    ).fetchone()[0]
    assert n > 0, (
        "Nenhum fornecedor de `contratos` aparece em `sancoes`. "
        "Provável bug em limpar_cnpj."
    )


def test_contratos_casam_com_socios(con):
    n = con.execute(
        "SELECT COUNT(DISTINCT c.cnpj_fornecedor) "
        "FROM contratos c JOIN socios so ON c.cnpj_fornecedor = so.cnpj"
    ).fetchone()[0]
    assert n > 0


def test_empresas_casam_com_sancoes(con):
    n = con.execute(
        "SELECT COUNT(DISTINCT e.cnpj) "
        "FROM empresas e JOIN sancoes s ON e.cnpj = s.cnpj"
    ).fetchone()[0]
    assert n > 0


def test_view_contratos_com_sancao_existe_e_nao_vazia(con):
    n = con.execute("SELECT COUNT(*) FROM vw_contratos_com_sancao").fetchone()[0]
    assert n > 0
