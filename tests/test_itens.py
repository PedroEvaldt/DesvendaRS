"""Validações específicas da tabela `itens` e da view de sobrepreço."""
from __future__ import annotations


def test_itens_tem_linhas(con):
    n = con.execute("SELECT COUNT(*) FROM itens").fetchone()[0]
    assert n > 0


def test_chave_composta_unica(con):
    """A chave (cd_orgao, nr_licitacao, ano, modalidade, lote, item) é única."""
    duplicadas = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT cd_orgao, nr_licitacao, ano_licitacao,
                   cd_tipo_modalidade, nr_lote, nr_item
              FROM itens
             GROUP BY 1,2,3,4,5,6
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    assert duplicadas == 0, f"{duplicadas} chaves compostas duplicadas em itens"


def test_descricao_normalizada_cobre_a_maioria(con):
    """A normalização deve ter sucesso na esmagadora maioria dos itens."""
    total, com_norm = con.execute(
        "SELECT COUNT(*), COUNT(descricao_normalizada) FROM itens"
    ).fetchone()
    assert com_norm / total > 0.95, (
        f"descricao_normalizada cobre só {com_norm}/{total} itens — algo quebrou"
    )


def test_grupos_com_massa_minima(con):
    """Existem grupos com massa estatística suficiente para detectar outliers."""
    grupos = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT 1 FROM itens
             WHERE descricao_normalizada IS NOT NULL
               AND valor_unitario_homologado IS NOT NULL
               AND unidade IS NOT NULL
             GROUP BY descricao_normalizada, unidade
            HAVING COUNT(*) >= 10
        )
        """
    ).fetchone()[0]
    assert grupos >= 100, (
        f"Só {grupos} grupos com massa >= 10. "
        "Normalização de descrição pode estar agrupando demais (ou de menos)."
    )


def test_vw_sobrepreco_devolve_indicios(con):
    """A view de sobrepreço precisa devolver pelo menos algumas dezenas de casos."""
    n = con.execute("SELECT COUNT(*) FROM vw_sobrepreco_indicios").fetchone()[0]
    assert n >= 50, (
        f"vw_sobrepreco_indicios devolveu só {n} linhas. "
        "Limiar (razão>=3, n>=10) pode estar muito restritivo."
    )


def test_itens_casam_com_contratos_via_cnpj(con):
    """Itens com CNPJ preenchido devem ter sobreposição com fornecedores em contratos.

    Não dá pra cruzar pela chave composta da licitação (contratos não a preserva),
    mas casar por cnpj_fornecedor já valida que limpar_cnpj é consistente entre as
    duas tabelas.
    """
    n = con.execute(
        "SELECT COUNT(DISTINCT i.cnpj_fornecedor) "
        "FROM itens i "
        "JOIN contratos c ON i.cnpj_fornecedor = c.cnpj_fornecedor "
        "WHERE i.cnpj_fornecedor IS NOT NULL"
    ).fetchone()[0]
    assert n > 0, (
        "Nenhum CNPJ de fornecedor em `itens` casa com `contratos`. "
        "Provável regressão em limpar_cnpj."
    )


def test_sobrepreco_razao_e_consistente(con):
    """Para cada linha da view, razao_vs_mediana = valor / mediana."""
    inconsistentes = con.execute(
        """
        SELECT COUNT(*) FROM vw_sobrepreco_indicios
         WHERE ABS(razao_vs_mediana - valor_unitario_homologado / mediana) > 0.0001
        """
    ).fetchone()[0]
    assert inconsistentes == 0
