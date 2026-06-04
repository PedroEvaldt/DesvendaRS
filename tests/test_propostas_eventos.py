"""Validações da Fase 3: propostas, propostas_itens, eventos_licitacao + views."""
from __future__ import annotations


# ---------- propostas ----------

def test_propostas_tem_linhas(con):
    n = con.execute("SELECT COUNT(*) FROM propostas").fetchone()[0]
    assert n > 0


def test_propostas_chave_composta_unica(con):
    """Uma proposta por (licitação × fornecedor)."""
    duplicadas = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT cd_orgao, nr_licitacao, ano_licitacao,
                   cd_tipo_modalidade, cnpj_proposta
              FROM propostas
             GROUP BY 1,2,3,4,5
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    assert duplicadas == 0


def test_propostas_resultado_proposta_codigos_conhecidos(con):
    """Resultado deve ser C (classificada), D (desclassificada) ou nulo."""
    inesperados = con.execute(
        "SELECT COUNT(DISTINCT resultado_proposta) "
        "FROM propostas "
        "WHERE resultado_proposta IS NOT NULL "
        "  AND resultado_proposta NOT IN ('C', 'D', 'P')"
    ).fetchone()[0]
    assert inesperados == 0, "propostas.resultado_proposta tem valor fora de C/D/P"


def test_propostas_cnpj_casa_com_contratos(con):
    """CNPJ de proposta deve aparecer em contratos (sanity de limpar_cnpj)."""
    n = con.execute(
        "SELECT COUNT(DISTINCT p.cnpj_proposta) "
        "FROM propostas p "
        "JOIN contratos c ON p.cnpj_proposta = c.cnpj_fornecedor"
    ).fetchone()[0]
    assert n > 0


# ---------- propostas_itens ----------

def test_propostas_itens_tem_linhas(con):
    n = con.execute("SELECT COUNT(*) FROM propostas_itens").fetchone()[0]
    assert n > 0


def test_propostas_itens_chave_composta_unica(con):
    """Uma proposta de item por (licitação × lote × item × fornecedor)."""
    duplicadas = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   nr_lote, nr_item, cnpj_proposta
              FROM propostas_itens
             GROUP BY 1,2,3,4,5,6,7
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    assert duplicadas == 0


# ---------- eventos_licitacao ----------

def test_eventos_tem_linhas(con):
    n = con.execute("SELECT COUNT(*) FROM eventos_licitacao").fetchone()[0]
    assert n > 0


def test_eventos_chave_sq_unica(con):
    """sq_evento é único dentro de cada licitação."""
    duplicadas = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT cd_orgao, nr_licitacao, ano_licitacao,
                   cd_tipo_modalidade, sq_evento
              FROM eventos_licitacao
             GROUP BY 1,2,3,4,5
            HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]
    assert duplicadas == 0


# ---------- views Fase 3 ----------

def test_vw_proposta_unica_devolve_resultados(con):
    n = con.execute("SELECT COUNT(*) FROM vw_proposta_unica").fetchone()[0]
    assert n > 0


def test_vw_proposta_unica_tem_exatamente_uma_classificada(con):
    """Por construção, qtd_propostas_classificadas = 1 em toda linha."""
    fora = con.execute(
        "SELECT COUNT(*) FROM vw_proposta_unica "
        "WHERE qtd_propostas_classificadas <> 1"
    ).fetchone()[0]
    assert fora == 0


def test_vw_cover_bidding_devolve_indicios(con):
    n = con.execute("SELECT COUNT(*) FROM vw_cover_bidding_indicios").fetchone()[0]
    assert n >= 50, (
        f"vw_cover_bidding_indicios devolveu só {n} linhas. "
        "Limiar (razão>=2x, n>=3) pode estar muito restritivo."
    )


def test_vw_cover_bidding_razao_e_consistente(con):
    inconsistentes = con.execute(
        "SELECT COUNT(*) FROM vw_cover_bidding_indicios "
        "WHERE ABS(razao_2a_vs_1a - valor_segunda / valor_vencedora) > 0.0001"
    ).fetchone()[0]
    assert inconsistentes == 0


def test_vw_alteracao_apos_abertura_devolve_resultados(con):
    n = con.execute("SELECT COUNT(*) FROM vw_alteracao_apos_abertura").fetchone()[0]
    assert n > 0


def test_vw_alteracao_apos_abertura_so_pos_publicacao(con):
    """Por construção, data_alteracao > data_publicacao em toda linha."""
    fora = con.execute(
        "SELECT COUNT(*) FROM vw_alteracao_apos_abertura "
        "WHERE data_alteracao <= data_publicacao"
    ).fetchone()[0]
    assert fora == 0
