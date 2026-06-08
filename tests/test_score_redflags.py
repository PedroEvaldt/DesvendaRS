"""Testes das tabelas de red flags e score."""
from __future__ import annotations

import duckdb
import pytest

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
        if meta.get("automatico", True):
            assert meta["pontos"] > 0
        assert meta["escopo"] in {"fornecedor", "licitacao", "item", "orgao", "llm"}
        assert meta["descricao"]


def _sinais_cenario_todas_redflags() -> set[str]:
    con = duckdb.connect(":memory:")
    try:
        _criar_schema_minimo(con)
        con.execute("DROP VIEW vw_cover_bidding_indicios")
        con.execute(
            """
            CREATE VIEW vw_cover_bidding_indicios AS
            SELECT 'ORGCOV' AS cd_orgao,
                   'COV1' AS nr_licitacao,
                   '2026' AS ano_licitacao,
                   'PRE' AS cd_tipo_modalidade,
                   3 AS n_classificadas,
                   '00000000000101' AS cnpj_vencedora,
                   100.00::DECIMAL(18,2) AS valor_vencedora,
                   '00000000000102' AS cnpj_segunda,
                   250.00::DECIMAL(18,2) AS valor_segunda,
                   2.5::DOUBLE AS razao_2a_vs_1a
            """
        )
        con.execute("DROP VIEW vw_alteracao_apos_abertura")
        con.execute(
            """
            CREATE VIEW vw_alteracao_apos_abertura AS
            SELECT 'ORGALT' AS cd_orgao,
                   'ALT1' AS nr_licitacao,
                   '2026' AS ano_licitacao,
                   'PRE' AS cd_tipo_modalidade,
                   'AED' AS cd_tipo_evento,
                   DATE '2026-01-01' AS data_publicacao,
                   DATE '2026-02-15' AS data_alteracao,
                   45 AS dias_apos_publicacao
            """
        )
        con.execute("DROP VIEW vw_sobrepreco_indicios")
        con.execute(
            """
            CREATE VIEW vw_sobrepreco_indicios AS
            SELECT *
              FROM (VALUES
                ('ORGSP','SP1','2026','PRE','1','1','00000000000101','ITEM A','UN',false,60.0::DECIMAL(18,4),10.0::DECIMAL(18,4),10,6.0::DOUBLE),
                ('ORGSP','SP2','2026','PRE','1','2','00000000000101','ITEM B','UN',false,40.0::DECIMAL(18,4),10.0::DECIMAL(18,4),10,4.0::DOUBLE),
                ('ORGSP','SP3','2026','PRE','1','3','00000000000101','ITEM C','UN',true,40.0::DECIMAL(18,4),10.0::DECIMAL(18,4),10,4.0::DOUBLE),
                ('ORGSP','SP4','2026','PRE','1','4','00000000000101','ITEM D','UN',false,35.0::DECIMAL(18,4),10.0::DECIMAL(18,4),10,3.5::DOUBLE),
                ('ORGSP','SP5','2026','PRE','1','5','00000000000101','ITEM E','UN',false,35.0::DECIMAL(18,4),10.0::DECIMAL(18,4),10,3.5::DOUBLE),
                ('ORGSP','SP6','2026','PRE','1','6','00000000000101','ITEM F','UN',false,35.0::DECIMAL(18,4),10.0::DECIMAL(18,4),10,3.5::DOUBLE),
                ('ORGSP','SP7','2026','PRE','1','7','00000000000101','ITEM G','UN',false,35.0::DECIMAL(18,4),10.0::DECIMAL(18,4),10,3.5::DOUBLE),
                ('ORGSP','SP8','2026','PRE','1','8','00000000000101','ITEM H','UN',false,35.0::DECIMAL(18,4),10.0::DECIMAL(18,4),10,3.5::DOUBLE),
                ('ORGSP','SP9','2026','PRE','1','9','00000000000101','ITEM I','UN',false,35.0::DECIMAL(18,4),10.0::DECIMAL(18,4),10,3.5::DOUBLE),
                ('ORGSP','SP10','2026','PRE','1','10','00000000000101','ITEM J','UN',false,35.0::DECIMAL(18,4),10.0::DECIMAL(18,4),10,3.5::DOUBLE)
              ) AS t(
                cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                nr_lote, nr_item, cnpj_fornecedor, descricao, unidade,
                flag_covid, valor_unitario_homologado, mediana, n_obs,
                razao_vs_mediana
              )
            """
        )
        con.execute(
            """
            INSERT INTO empresas VALUES
            ('00000000000101', 'A', DATE '2025-12-01', '1', 500.00, '8', 'ME', 'RUA COMPARTILHADA 100', 'X'),
            ('00000000000102', 'B', DATE '2020-01-01', '1', 10000.00, '2', 'ME', 'RUA COMPARTILHADA 100', 'X'),
            ('00000000000103', 'C', DATE '2020-01-01', '1', 10000.00, '2', 'ME', 'RUA C 100', 'X'),
            ('00000000000104', 'D', DATE '2020-01-01', '1', 10000.00, '2', 'ME', 'RUA D 100', 'X')
            """
        )
        con.execute(
            """
            INSERT INTO socios VALUES
            ('00000000000101', 'SOCIO A', '***123456**', 'PF', 'SOCIO', DATE '2025-12-15'),
            ('00000000000102', 'SOCIO B', '***123456**', 'PF', 'SOCIO', DATE '2020-01-01')
            """
        )
        con.execute(
            """
            INSERT INTO sancoes VALUES
            ('00000000000101', 'IMPEDIMENTO', 'ORGAO', DATE '2026-01-01', DATE '2026-12-31', 'CEIS'),
            ('00000000000102', 'SUSPENSAO', 'ORGAO', DATE '2025-01-01', DATE '2025-06-01', 'CFIL')
            """
        )
        con.execute(
            """
            INSERT INTO contratos VALUES
            ('00000000000101','A','ORGAO A','M','PRE','OBJ A',200000.00,DATE '2026-01-10','A1',1,false),
            ('00000000000101','A','ORGAO A','M','PRE','OBJ A',60000.00,DATE '2026-02-10','A2',1,false),
            ('00000000000101','A','ORGAO A','M','PRE','OBJ A',50000.00,DATE '2026-03-10','A3',1,false),
            ('00000000000102','B','ORGAO REC','M','PRE','OBJ REC',50000.00,DATE '2026-01-10','R1',3,false),
            ('00000000000102','B','ORGAO REC','M','PRE','OBJ REC',50000.00,DATE '2026-02-10','R2',3,false),
            ('00000000000102','B','ORGAO REC','M','PRE','OBJ REC',50000.00,DATE '2026-03-10','R3',3,false),
            ('00000000000103','C','ORGAO FRAC','M','DSP','OBJ FRAC',60000.00,DATE '2026-01-10','F1',1,false),
            ('00000000000103','C','ORGAO FRAC','M','DSP','OBJ FRAC',60000.00,DATE '2026-02-10','F2',1,false),
            ('00000000000103','C','ORGAO FRAC','M','DSP','OBJ ALTO',150000.00,DATE '2026-03-10','F3',1,false)
            """
        )
        for i in range(10):
            con.execute(
                """
                INSERT INTO contratos VALUES
                ('00000000000104','D','ORGAO DISP','M','DSP','OBJ DISP',
                 1000.00, DATE '2026-04-01', ?, 1, false)
                """,
                [f"D{i}"],
            )
        for i in range(10):
            estimado = 40 if i == 9 else 10
            con.execute(
                """
                INSERT INTO itens VALUES
                ('ORGI','EST','2026','PRE','1', ?, '00000000000101',
                 'ITEM EST', 'item-est', 1, 'UN', ?, 10, 10, false)
                """,
                [str(i + 1), estimado],
            )
        for i in range(1, 6):
            valores = (100, 200) if i <= 3 else (200, 100)
            con.execute(
                """
                INSERT INTO propostas VALUES
                ('ORGCAR', ?, '2026', 'PRE', '00000000000101',
                 DATE '2026-01-10', 'C', ?, 1, NULL, NULL),
                ('ORGCAR', ?, '2026', 'PRE', '00000000000102',
                 DATE '2026-01-10', 'C', ?, 1, NULL, NULL)
                """,
                [f"C{i}", valores[0], f"C{i}", valores[1]],
            )
        con.execute(
            """
            INSERT INTO propostas VALUES
            ('ORGONE','ONE1','2026','PRE','00000000000101',DATE '2026-01-10','C',100,0,NULL,NULL),
            ('ORGPROX','P1','2026','PRE','00000000000101',DATE '2026-01-10','C',100.0,0,NULL,NULL),
            ('ORGPROX','P1','2026','PRE','00000000000102',DATE '2026-01-10','C',100.5,0,NULL,NULL),
            ('ORGPROX','P1','2026','PRE','00000000000103',DATE '2026-01-10','C',101.0,0,NULL,NULL),
            ('ORGALT','ALT1','2026','PRE','00000000000101',DATE '2026-01-02','C',100,0,NULL,NULL),
            ('ORGALT','ALT1','2026','PRE','00000000000102',DATE '2026-01-02','C',200,0,NULL,NULL)
            """
        )
        for i in range(10):
            con.execute(
                """
                INSERT INTO propostas VALUES
                ('ORGBC', ?, '2026', 'PRE', '00000000000101',
                 DATE '2026-01-10', 'C', 100, 0, NULL, NULL)
                """,
                [f"B{i}"],
            )
        con.execute(
            """
            INSERT INTO propostas_itens VALUES
            ('ORGITEM','I1','2026','PRE','1','1','00000000000101',10,10,0,NULL,NULL,NULL,'D','INABILITADO'),
            ('ORGITEM','I1','2026','PRE','1','1','00000000000102',25,25,0,NULL,NULL,NULL,'C','HABILITADO'),
            ('ORGITEM','I1','2026','PRE','1','1','00000000000103',30,30,0,NULL,NULL,NULL,'C','HABILITADO')
            """
        )
        con.execute(
            """
            INSERT INTO eventos_licitacao VALUES
            ('ORGALT','ALT1','2026','PRE','1','F','PUE',DATE '2026-01-01','WEB','PUB',NULL,NULL,NULL,NULL,NULL),
            ('ORGALT','ALT1','2026','PRE','2','F','AED',DATE '2026-01-02','WEB','ALT',NULL,NULL,NULL,NULL,NULL),
            ('ORGANO','AN1','2026','PRE','1','F','ANO',DATE '2026-01-01','WEB','AN',NULL,NULL,NULL,NULL,NULL),
            ('ORGANO','AN2','2026','PRE','2','F','ANO',DATE '2026-01-02','WEB','AN',NULL,NULL,NULL,NULL,NULL),
            ('ORGANO','AN3','2026','PRE','3','F','SUO',DATE '2026-01-03','WEB','SU',NULL,NULL,NULL,NULL,NULL),
            ('ORGANO','AN4','2026','PRE','4','F','SUO',DATE '2026-01-04','WEB','SU',NULL,NULL,NULL,NULL,NULL),
            ('ORGANO','AN5','2026','PRE','5','F','ANO',DATE '2026-01-05','WEB','AN',NULL,NULL,NULL,NULL,NULL)
            """
        )

        criar_tabelas_score(con)

        return {
            row[0]
            for row in con.execute("SELECT DISTINCT sinal FROM redflag_eventos").fetchall()
        }
    finally:
        con.close()


RED_FLAGS_AUTOMATICAS = [
    sinal for sinal, meta in RED_FLAGS.items() if meta.get("automatico", True)
]


@pytest.fixture(scope="module")
def sinais_cenario_todas_redflags() -> set[str]:
    return _sinais_cenario_todas_redflags()


def test_todas_redflags_automaticas_estao_no_cenario_de_teste(sinais_cenario_todas_redflags):
    sinais = sinais_cenario_todas_redflags
    assert set(RED_FLAGS_AUTOMATICAS) == sinais


@pytest.mark.parametrize("sinal", RED_FLAGS_AUTOMATICAS, ids=RED_FLAGS_AUTOMATICAS)
def test_redflag_automatica_aciona(sinal, sinais_cenario_todas_redflags):
    sinais = sinais_cenario_todas_redflags
    assert sinal in sinais


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
