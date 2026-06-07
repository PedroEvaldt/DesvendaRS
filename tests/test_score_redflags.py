"""Testes das tabelas de red flags e score."""
from __future__ import annotations

import duckdb

from etl.score_redflags import RED_FLAGS, criar_tabelas_score


def _criar_schema_minimo(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE contratos (
            cnpj_fornecedor VARCHAR,
            razao_social VARCHAR,
            orgao VARCHAR,
            municipio VARCHAR,
            modalidade VARCHAR,
            objeto VARCHAR,
            valor_contrato DECIMAL(18,2),
            data_contrato DATE,
            numero_contrato VARCHAR,
            qtd_participantes INTEGER,
            flag_covid BOOLEAN
        )
        """
    )
    con.execute(
        """
        CREATE TABLE empresas (
            cnpj VARCHAR,
            razao_social VARCHAR,
            data_abertura DATE,
            cnae VARCHAR,
            capital_social DECIMAL(18,2),
            situacao_cadastral VARCHAR,
            porte VARCHAR,
            endereco VARCHAR,
            municipio VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE socios (
            cnpj VARCHAR,
            nome_socio VARCHAR,
            doc_socio VARCHAR,
            tipo_socio VARCHAR,
            qualificacao VARCHAR,
            data_entrada DATE
        )
        """
    )
    con.execute(
        """
        CREATE TABLE sancoes (
            cnpj VARCHAR,
            tipo_sancao VARCHAR,
            orgao_sancionador VARCHAR,
            data_inicio DATE,
            data_fim DATE,
            fonte VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE itens (
            cd_orgao VARCHAR,
            nr_licitacao VARCHAR,
            ano_licitacao VARCHAR,
            cd_tipo_modalidade VARCHAR,
            nr_lote VARCHAR,
            nr_item VARCHAR,
            cnpj_fornecedor VARCHAR,
            descricao VARCHAR,
            descricao_normalizada VARCHAR,
            quantidade DECIMAL(18,4),
            unidade VARCHAR,
            valor_unitario_estimado DECIMAL(18,4),
            valor_unitario_homologado DECIMAL(18,4),
            valor_total_homologado DECIMAL(18,2),
            flag_covid BOOLEAN
        )
        """
    )
    con.execute(
        """
        CREATE TABLE propostas (
            cd_orgao VARCHAR,
            nr_licitacao VARCHAR,
            ano_licitacao VARCHAR,
            cd_tipo_modalidade VARCHAR,
            cnpj_proposta VARCHAR,
            data_proposta DATE,
            resultado_proposta VARCHAR,
            valor_total_proposta DECIMAL(18,2),
            percentual_desconto DECIMAL(8,4),
            valor_nota_tecnica DECIMAL(18,4),
            data_homologacao DATE
        )
        """
    )
    con.execute(
        """
        CREATE TABLE propostas_itens (
            cd_orgao VARCHAR,
            nr_licitacao VARCHAR,
            ano_licitacao VARCHAR,
            cd_tipo_modalidade VARCHAR,
            nr_lote VARCHAR,
            nr_item VARCHAR,
            cnpj_proposta VARCHAR,
            valor_unitario DECIMAL(18,4),
            valor_total_item DECIMAL(18,2),
            percentual_desconto DECIMAL(8,4),
            percentual_bdi DECIMAL(8,4),
            valor_nota_tecnica DECIMAL(18,4),
            data_homologacao DATE,
            resultado_proposta VARCHAR,
            resultado_habilitacao VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE eventos_licitacao (
            cd_orgao VARCHAR,
            nr_licitacao VARCHAR,
            ano_licitacao VARCHAR,
            cd_tipo_modalidade VARCHAR,
            sq_evento VARCHAR,
            cd_tipo_fase VARCHAR,
            cd_tipo_evento VARCHAR,
            data_evento DATE,
            tipo_veiculo_publicacao VARCHAR,
            descricao_publicacao VARCHAR,
            cnpj_autor VARCHAR,
            data_julgamento DATE,
            tipo_resultado VARCHAR,
            nr_lote VARCHAR,
            nr_item VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE VIEW vw_proposta_unica AS
        SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               COUNT(*) AS qtd_propostas_classificadas
          FROM propostas
         WHERE resultado_proposta = 'C'
         GROUP BY 1,2,3,4
        HAVING COUNT(*) = 1
        """
    )
    con.execute(
        """
        CREATE VIEW vw_cover_bidding_indicios AS
        SELECT * FROM (
            SELECT NULL::VARCHAR AS cd_orgao,
                   NULL::VARCHAR AS nr_licitacao,
                   NULL::VARCHAR AS ano_licitacao,
                   NULL::VARCHAR AS cd_tipo_modalidade,
                   NULL::INTEGER AS n_classificadas,
                   NULL::VARCHAR AS cnpj_vencedora,
                   NULL::DECIMAL(18,2) AS valor_vencedora,
                   NULL::VARCHAR AS cnpj_segunda,
                   NULL::DECIMAL(18,2) AS valor_segunda,
                   NULL::DOUBLE AS razao_2a_vs_1a
        ) WHERE 1 = 0
        """
    )
    con.execute(
        """
        CREATE VIEW vw_alteracao_apos_abertura AS
        SELECT * FROM (
            SELECT NULL::VARCHAR AS cd_orgao,
                   NULL::VARCHAR AS nr_licitacao,
                   NULL::VARCHAR AS ano_licitacao,
                   NULL::VARCHAR AS cd_tipo_modalidade,
                   NULL::VARCHAR AS cd_tipo_evento,
                   NULL::DATE AS data_publicacao,
                   NULL::DATE AS data_alteracao,
                   NULL::INTEGER AS dias_apos_publicacao
        ) WHERE 1 = 0
        """
    )
    con.execute(
        """
        CREATE VIEW vw_sobrepreco_indicios AS
        SELECT * FROM (
            SELECT NULL::VARCHAR AS cd_orgao,
                   NULL::VARCHAR AS nr_licitacao,
                   NULL::VARCHAR AS ano_licitacao,
                   NULL::VARCHAR AS cd_tipo_modalidade,
                   NULL::VARCHAR AS nr_lote,
                   NULL::VARCHAR AS nr_item,
                   NULL::VARCHAR AS cnpj_fornecedor,
                   NULL::VARCHAR AS descricao,
                   NULL::VARCHAR AS unidade,
                   NULL::BOOLEAN AS flag_covid,
                   NULL::DECIMAL(18,4) AS valor_unitario_homologado,
                   NULL::DECIMAL(18,4) AS mediana,
                   NULL::INTEGER AS n_obs,
                   NULL::DOUBLE AS razao_vs_mediana
        ) WHERE 1 = 0
        """
    )


def test_red_flags_tem_peso_escopo_e_descricao():
    assert RED_FLAGS
    for sinal, meta in RED_FLAGS.items():
        assert sinal
        assert isinstance(meta["pontos"], int)
        assert meta["pontos"] > 0
        assert meta["escopo"] in {"fornecedor", "licitacao", "item"}
        assert meta["descricao"]


def test_criar_tabelas_score_marca_possivel_fraude_por_score_bruto():
    con = duckdb.connect(":memory:")
    try:
        _criar_schema_minimo(con)
        con.execute(
            """
            INSERT INTO contratos VALUES
            ('00000000000191', 'ACME', 'PM DE TESTE', 'TESTE', 'PREGAO', 'OBJ',
             200000.00, DATE '2026-01-10', '1', 1, false),
            ('00000000000191', 'ACME', 'PM DE TESTE', 'TESTE', 'PREGAO', 'OBJ',
             1000.00, DATE '2025-08-01', '2', 1, false)
            """
        )
        con.execute(
            """
            INSERT INTO empresas VALUES
            ('00000000000191', 'ACME', DATE '2025-12-01', '1', 500.00,
             '8', 'ME', 'RUA A', 'TESTE')
            """
        )
        con.execute(
            """
            INSERT INTO socios VALUES
            ('00000000000191', 'SOCIO', '***123456**', 'PF', 'SOCIO',
             DATE '2025-12-15')
            """
        )
        con.execute(
            """
            INSERT INTO sancoes VALUES
            ('00000000000191', 'IMPEDIMENTO', 'ORGAO', DATE '2025-01-01',
             DATE '2025-06-01', 'CEIS'),
            ('00000000000191', 'SUSPENSAO', 'ORGAO', DATE '2026-01-01',
             DATE '2026-12-31', 'CFIL')
            """
        )

        criar_tabelas_score(con)

        score = con.execute(
            "SELECT score_bruto, score, possivel_fraude FROM scores_fornecedor"
        ).fetchone()
        assert score == (126, 100, True)

        sinais = {
            row[0]
            for row in con.execute(
                "SELECT DISTINCT sinal FROM redflag_eventos WHERE escopo = 'fornecedor'"
            ).fetchall()
        }
        assert "indicio_sancionado_ativo" in sinais
        assert "indicio_sancionado_historico" in sinais
        assert "indicio_empresa_inativa_com_contrato" in sinais
    finally:
        con.close()
