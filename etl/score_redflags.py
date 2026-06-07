"""Calcula red flags e scores explicaveis no DuckDB.

O modulo grava eventos atomicos de red flag em `redflag_eventos` e agrega esses
eventos em tabelas de score por fornecedor, licitacao e item. O `score_bruto`
pode passar de 100; `score` fica capado em 100 para ranking.
"""
from __future__ import annotations

import logging

import duckdb

log = logging.getLogger(__name__)

LIMIAR_POSSIVEL_FRAUDE = 100

RED_FLAGS: dict[str, dict[str, object]] = {
    "indicio_sancionado_ativo": {
        "pontos": 30,
        "forca": "Forte",
        "escopo": "fornecedor",
        "descricao": "Fornecedor tem sancao vigente na data do contrato.",
    },
    "indicio_sancionado_historico": {
        "pontos": 12,
        "forca": "Media",
        "escopo": "fornecedor",
        "descricao": "Fornecedor aparece em lista de sancoes fora da janela do contrato.",
    },
    "indicio_empresa_inativa_com_contrato": {
        "pontos": 22,
        "forca": "Forte",
        "escopo": "fornecedor",
        "descricao": "Empresa com situacao cadastral diferente de ativa possui contrato.",
    },
    "indicio_empresa_jovem_contrato_grande": {
        "pontos": 10,
        "forca": "Media",
        "escopo": "fornecedor",
        "descricao": "Empresa aberta ha menos de 180 dias recebeu contrato acima de R$ 100 mil.",
    },
    "indicio_capital_baixo": {
        "pontos": 8,
        "forca": "Media",
        "escopo": "fornecedor",
        "descricao": "Valor do contrato e mais de 10 vezes o capital social.",
    },
    "indicio_capital_irrisorio_contrato_alto": {
        "pontos": 12,
        "forca": "Media",
        "escopo": "fornecedor",
        "descricao": "Capital social ate R$ 1 mil combinado com contrato acima de R$ 100 mil.",
    },
    "indicio_socio_recente_antes_contrato": {
        "pontos": 10,
        "forca": "Media",
        "escopo": "fornecedor",
        "descricao": "Socio entrou ate 180 dias antes de contrato acima de R$ 100 mil.",
    },
    "alerta_competicao_zero": {
        "pontos": 22,
        "forca": "Forte",
        "escopo": "licitacao",
        "descricao": "Licitacao tem exatamente uma proposta classificada.",
    },
    "alerta_cover_bidding": {
        "pontos": 15,
        "forca": "Media",
        "escopo": "licitacao",
        "descricao": "Segunda menor proposta e pelo menos 2 vezes a menor proposta.",
    },
    "indicio_propostas_muito_proximas": {
        "pontos": 12,
        "forca": "Media",
        "escopo": "licitacao",
        "descricao": "Propostas classificadas tem coeficiente de variacao ate 1%.",
    },
    "indicio_cartel_recorrente": {
        "pontos": 12,
        "forca": "Media",
        "escopo": "licitacao",
        "descricao": "Par de CNPJs concorre junto em 5 ou mais licitacoes.",
    },
    "indicio_segundo_colocado_recorrente": {
        "pontos": 15,
        "forca": "Media",
        "escopo": "licitacao",
        "descricao": "Mesmo par vencedor/segundo colocado se repete em 3 ou mais licitacoes.",
    },
    "alerta_alteracao_regra_tardia": {
        "pontos": 10,
        "forca": "Media",
        "escopo": "licitacao",
        "descricao": "Alteracao ou republicacao ocorre mais de 30 dias apos a primeira publicacao.",
    },
    "alerta_sobrepreco_alto": {
        "pontos": 18,
        "forca": "Media/Forte",
        "escopo": "item",
        "descricao": "Item homologado custa ao menos 5 vezes a mediana do grupo comparavel.",
    },
    "alerta_sobrepreco_moderado": {
        "pontos": 6,
        "forca": "Fraca/Media",
        "escopo": "item",
        "descricao": "Item homologado custa entre 3 e 5 vezes a mediana do grupo comparavel.",
    },
    "alerta_covid_sobrepreco": {
        "pontos": 10,
        "forca": "Media",
        "escopo": "item",
        "descricao": "Item COVID tambem apresenta indicio de sobrepreco.",
    },
    "indicio_preco_estimado_acima_mediana": {
        "pontos": 15,
        "forca": "Media/Forte",
        "escopo": "item",
        "descricao": "Valor unitario estimado esta ao menos 3 vezes acima da mediana historica.",
    },
    "indicio_proposta_item_perdedora_artificialmente_alta": {
        "pontos": 12,
        "forca": "Media",
        "escopo": "item",
        "descricao": "Segunda menor proposta de item e pelo menos 2 vezes a menor.",
    },
    "indicio_desclassificacao_conveniente": {
        "pontos": 20,
        "forca": "Forte",
        "escopo": "item",
        "descricao": "Proposta mais barata foi desclassificada e ha classificada mais cara.",
    },
}


def criar_tabelas_score(
    con: duckdb.DuckDBPyConnection,
    *,
    limiar_possivel_fraude: int = LIMIAR_POSSIVEL_FRAUDE,
) -> None:
    """Recalcula red flags e scores a partir das tabelas analiticas."""
    log.info("Calculando red flags e scores")
    _criar_tabela_eventos(con)
    _inserir_redflags_fornecedor(con)
    _inserir_redflags_licitacao(con)
    _inserir_redflags_item(con)
    _criar_scores_agregados(con, limiar_possivel_fraude)


def _meta(sinal: str) -> tuple[int, str]:
    info = RED_FLAGS[sinal]
    return int(info["pontos"]), str(info["forca"])


def _criar_tabela_eventos(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("DROP TABLE IF EXISTS redflag_eventos")
    con.execute(
        """
        CREATE TABLE redflag_eventos (
            escopo VARCHAR,
            entidade_id VARCHAR,
            cd_orgao VARCHAR,
            nr_licitacao VARCHAR,
            ano_licitacao VARCHAR,
            cd_tipo_modalidade VARCHAR,
            nr_lote VARCHAR,
            nr_item VARCHAR,
            cnpj VARCHAR,
            sinal VARCHAR,
            pontos INTEGER,
            forca VARCHAR,
            evidencia VARCHAR
        )
        """
    )


def _insert(con: duckdb.DuckDBPyConnection, sinal: str, sql_select: str) -> None:
    pontos, forca = _meta(sinal)
    con.execute(
        f"""
        INSERT INTO redflag_eventos
        SELECT escopo, entidade_id, cd_orgao, nr_licitacao, ano_licitacao,
               cd_tipo_modalidade, nr_lote, nr_item, cnpj, sinal,
               {pontos} AS pontos, '{forca}' AS forca, evidencia
          FROM ({sql_select}) t
        """
    )


def _inserir_redflags_fornecedor(con: duckdb.DuckDBPyConnection) -> None:
    _insert(
        con,
        "indicio_sancionado_ativo",
        """
        SELECT 'fornecedor' AS escopo,
               c.cnpj_fornecedor AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               NULL AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               c.cnpj_fornecedor AS cnpj,
               'indicio_sancionado_ativo' AS sinal,
               'fonte=' || COALESCE(s.fonte, '?') ||
               '; contrato=' || COALESCE(CAST(c.data_contrato AS VARCHAR), '?') ||
               '; sancao=' || COALESCE(CAST(s.data_inicio AS VARCHAR), '?') ||
               '..' || COALESCE(CAST(s.data_fim AS VARCHAR), 'aberta') AS evidencia
          FROM contratos c
          JOIN sancoes s ON c.cnpj_fornecedor = s.cnpj
         WHERE c.data_contrato IS NOT NULL
           AND c.data_contrato >= COALESCE(s.data_inicio, DATE '1900-01-01')
           AND c.data_contrato <= COALESCE(s.data_fim, DATE '2100-12-31')
        """,
    )
    _insert(
        con,
        "indicio_sancionado_historico",
        """
        SELECT 'fornecedor' AS escopo,
               c.cnpj_fornecedor AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               NULL AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               c.cnpj_fornecedor AS cnpj,
               'indicio_sancionado_historico' AS sinal,
               'fonte=' || COALESCE(s.fonte, '?') ||
               '; sancao=' || COALESCE(CAST(s.data_inicio AS VARCHAR), '?') ||
               '..' || COALESCE(CAST(s.data_fim AS VARCHAR), 'aberta') AS evidencia
         FROM contratos c
          JOIN sancoes s ON c.cnpj_fornecedor = s.cnpj
         WHERE c.cnpj_fornecedor IS NOT NULL
           AND (
               c.data_contrato IS NULL
               OR s.data_inicio IS NULL
               OR s.data_inicio <= c.data_contrato
           )
           AND NOT EXISTS (
               SELECT 1
                 FROM sancoes ativa
                WHERE ativa.cnpj = c.cnpj_fornecedor
                  AND c.data_contrato IS NOT NULL
                  AND c.data_contrato >= COALESCE(ativa.data_inicio, DATE '1900-01-01')
                  AND c.data_contrato <= COALESCE(ativa.data_fim, DATE '2100-12-31')
           )
        """,
    )
    _insert(
        con,
        "indicio_empresa_inativa_com_contrato",
        """
        SELECT 'fornecedor' AS escopo,
               c.cnpj_fornecedor AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               NULL AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               c.cnpj_fornecedor AS cnpj,
               'indicio_empresa_inativa_com_contrato' AS sinal,
               'situacao_cadastral=' || COALESCE(e.situacao_cadastral, '?') AS evidencia
          FROM contratos c
          JOIN empresas e ON c.cnpj_fornecedor = e.cnpj
         WHERE e.situacao_cadastral IS NOT NULL
           AND TRIM(UPPER(e.situacao_cadastral)) <> '2'
           AND TRIM(UPPER(e.situacao_cadastral)) NOT LIKE '%ATIVA%'
        """,
    )
    _insert(
        con,
        "indicio_empresa_jovem_contrato_grande",
        """
        SELECT 'fornecedor' AS escopo,
               c.cnpj_fornecedor AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               NULL AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               c.cnpj_fornecedor AS cnpj,
               'indicio_empresa_jovem_contrato_grande' AS sinal,
               'abertura=' || CAST(e.data_abertura AS VARCHAR) ||
               '; contrato=' || CAST(c.data_contrato AS VARCHAR) ||
               '; valor=' || CAST(c.valor_contrato AS VARCHAR) AS evidencia
          FROM contratos c
          JOIN empresas e ON c.cnpj_fornecedor = e.cnpj
         WHERE e.data_abertura IS NOT NULL
           AND c.data_contrato IS NOT NULL
           AND c.valor_contrato > 100000
           AND c.data_contrato >= e.data_abertura
           AND c.data_contrato - e.data_abertura < 180
        """,
    )
    _insert(
        con,
        "indicio_capital_baixo",
        """
        SELECT 'fornecedor' AS escopo,
               c.cnpj_fornecedor AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               NULL AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               c.cnpj_fornecedor AS cnpj,
               'indicio_capital_baixo' AS sinal,
               'valor=' || CAST(c.valor_contrato AS VARCHAR) ||
               '; capital=' || CAST(e.capital_social AS VARCHAR) AS evidencia
          FROM contratos c
          JOIN empresas e ON c.cnpj_fornecedor = e.cnpj
         WHERE c.valor_contrato IS NOT NULL
           AND e.capital_social IS NOT NULL
           AND e.capital_social > 0
           AND c.valor_contrato > e.capital_social * 10
        """,
    )
    _insert(
        con,
        "indicio_capital_irrisorio_contrato_alto",
        """
        SELECT 'fornecedor' AS escopo,
               c.cnpj_fornecedor AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               NULL AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               c.cnpj_fornecedor AS cnpj,
               'indicio_capital_irrisorio_contrato_alto' AS sinal,
               'valor=' || CAST(c.valor_contrato AS VARCHAR) ||
               '; capital=' || COALESCE(CAST(e.capital_social AS VARCHAR), '?') AS evidencia
          FROM contratos c
          JOIN empresas e ON c.cnpj_fornecedor = e.cnpj
         WHERE c.valor_contrato > 100000
           AND COALESCE(e.capital_social, 0) <= 1000
        """,
    )
    _insert(
        con,
        "indicio_socio_recente_antes_contrato",
        """
        SELECT 'fornecedor' AS escopo,
               c.cnpj_fornecedor AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               NULL AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               c.cnpj_fornecedor AS cnpj,
               'indicio_socio_recente_antes_contrato' AS sinal,
               'socio=' || COALESCE(s.nome_socio, '?') ||
               '; entrada=' || CAST(s.data_entrada AS VARCHAR) ||
               '; contrato=' || CAST(c.data_contrato AS VARCHAR) ||
               '; valor=' || CAST(c.valor_contrato AS VARCHAR) AS evidencia
          FROM contratos c
          JOIN socios s ON c.cnpj_fornecedor = s.cnpj
         WHERE s.data_entrada IS NOT NULL
           AND c.data_contrato IS NOT NULL
           AND c.valor_contrato > 100000
           AND s.data_entrada <= c.data_contrato
           AND c.data_contrato - s.data_entrada <= 180
        """,
    )


def _inserir_redflags_licitacao(con: duckdb.DuckDBPyConnection) -> None:
    lic_id = (
        "cd_orgao || '|' || nr_licitacao || '|' || ano_licitacao || '|' || "
        "cd_tipo_modalidade"
    )
    _insert(
        con,
        "alerta_competicao_zero",
        f"""
        SELECT 'licitacao' AS escopo, {lic_id} AS entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, NULL AS cnpj,
               'alerta_competicao_zero' AS sinal,
               'qtd_propostas_classificadas=' ||
               CAST(qtd_propostas_classificadas AS VARCHAR) AS evidencia
          FROM vw_proposta_unica
        """,
    )
    _insert(
        con,
        "alerta_cover_bidding",
        f"""
        SELECT 'licitacao' AS escopo, {lic_id} AS entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, cnpj_vencedora AS cnpj,
               'alerta_cover_bidding' AS sinal,
               'vencedora=' || cnpj_vencedora ||
               '; segunda=' || cnpj_segunda ||
               '; razao=' || CAST(razao_2a_vs_1a AS VARCHAR) AS evidencia
          FROM vw_cover_bidding_indicios
        """,
    )
    _insert(
        con,
        "indicio_propostas_muito_proximas",
        """
        WITH stats AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   COUNT(*) AS n,
                   AVG(valor_total_proposta) AS media,
                   STDDEV_POP(valor_total_proposta) AS desvio
              FROM propostas
             WHERE resultado_proposta = 'C'
               AND valor_total_proposta IS NOT NULL
               AND valor_total_proposta > 0
             GROUP BY 1,2,3,4
        )
        SELECT 'licitacao' AS escopo,
               cd_orgao || '|' || nr_licitacao || '|' || ano_licitacao || '|' ||
               cd_tipo_modalidade AS entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, NULL AS cnpj,
               'indicio_propostas_muito_proximas' AS sinal,
               'n=' || CAST(n AS VARCHAR) ||
               '; coef_variacao=' || CAST(desvio / media AS VARCHAR) AS evidencia
          FROM stats
         WHERE n >= 3
           AND media > 0
           AND desvio / media <= 0.01
        """,
    )
    _insert(
        con,
        "indicio_cartel_recorrente",
        """
        WITH pares AS (
            SELECT p1.cnpj_proposta AS cnpj_a, p2.cnpj_proposta AS cnpj_b,
                   COUNT(DISTINCT p1.cd_orgao || '|' || p1.nr_licitacao || '|' ||
                          p1.ano_licitacao || '|' || p1.cd_tipo_modalidade) AS n_juntas
              FROM propostas p1
              JOIN propostas p2
                ON p1.cd_orgao = p2.cd_orgao
               AND p1.nr_licitacao = p2.nr_licitacao
               AND p1.ano_licitacao = p2.ano_licitacao
               AND p1.cd_tipo_modalidade = p2.cd_tipo_modalidade
               AND p1.cnpj_proposta < p2.cnpj_proposta
             GROUP BY 1,2
            HAVING COUNT(DISTINCT p1.cd_orgao || '|' || p1.nr_licitacao || '|' ||
                          p1.ano_licitacao || '|' || p1.cd_tipo_modalidade) >= 5
        )
        SELECT 'licitacao' AS escopo,
               p1.cd_orgao || '|' || p1.nr_licitacao || '|' || p1.ano_licitacao ||
               '|' || p1.cd_tipo_modalidade AS entidade_id,
               p1.cd_orgao, p1.nr_licitacao, p1.ano_licitacao, p1.cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, p1.cnpj_proposta AS cnpj,
               'indicio_cartel_recorrente' AS sinal,
               'par=' || pares.cnpj_a || '/' || pares.cnpj_b ||
               '; licitacoes_juntas=' || CAST(pares.n_juntas AS VARCHAR) AS evidencia
          FROM propostas p1
          JOIN propostas p2
            ON p1.cd_orgao = p2.cd_orgao
           AND p1.nr_licitacao = p2.nr_licitacao
           AND p1.ano_licitacao = p2.ano_licitacao
           AND p1.cd_tipo_modalidade = p2.cd_tipo_modalidade
           AND p1.cnpj_proposta < p2.cnpj_proposta
          JOIN pares
            ON p1.cnpj_proposta = pares.cnpj_a
           AND p2.cnpj_proposta = pares.cnpj_b
        """,
    )
    _insert(
        con,
        "indicio_segundo_colocado_recorrente",
        """
        WITH rankeadas AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   cnpj_proposta, valor_total_proposta,
                   ROW_NUMBER() OVER (
                       PARTITION BY cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade
                       ORDER BY valor_total_proposta ASC
                   ) AS posicao
              FROM propostas
             WHERE resultado_proposta = 'C'
               AND valor_total_proposta IS NOT NULL
               AND valor_total_proposta > 0
        ),
        pares AS (
            SELECT r1.cnpj_proposta AS cnpj_vencedora,
                   r2.cnpj_proposta AS cnpj_segunda,
                   COUNT(*) AS repeticoes
              FROM rankeadas r1
              JOIN rankeadas r2
                ON r1.cd_orgao = r2.cd_orgao
               AND r1.nr_licitacao = r2.nr_licitacao
               AND r1.ano_licitacao = r2.ano_licitacao
               AND r1.cd_tipo_modalidade = r2.cd_tipo_modalidade
             WHERE r1.posicao = 1 AND r2.posicao = 2
             GROUP BY 1,2
            HAVING COUNT(*) >= 3
        )
        SELECT 'licitacao' AS escopo,
               r1.cd_orgao || '|' || r1.nr_licitacao || '|' || r1.ano_licitacao ||
               '|' || r1.cd_tipo_modalidade AS entidade_id,
               r1.cd_orgao, r1.nr_licitacao, r1.ano_licitacao, r1.cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, r1.cnpj_proposta AS cnpj,
               'indicio_segundo_colocado_recorrente' AS sinal,
               'vencedora=' || r1.cnpj_proposta ||
               '; segunda=' || r2.cnpj_proposta ||
               '; repeticoes=' || CAST(pares.repeticoes AS VARCHAR) AS evidencia
          FROM rankeadas r1
          JOIN rankeadas r2
            ON r1.cd_orgao = r2.cd_orgao
           AND r1.nr_licitacao = r2.nr_licitacao
           AND r1.ano_licitacao = r2.ano_licitacao
           AND r1.cd_tipo_modalidade = r2.cd_tipo_modalidade
          JOIN pares
            ON r1.cnpj_proposta = pares.cnpj_vencedora
           AND r2.cnpj_proposta = pares.cnpj_segunda
         WHERE r1.posicao = 1 AND r2.posicao = 2
        """,
    )
    _insert(
        con,
        "alerta_alteracao_regra_tardia",
        f"""
        SELECT 'licitacao' AS escopo, {lic_id} AS entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, NULL AS cnpj,
               'alerta_alteracao_regra_tardia' AS sinal,
               'evento=' || cd_tipo_evento ||
               '; dias_apos_publicacao=' || CAST(dias_apos_publicacao AS VARCHAR) AS evidencia
          FROM vw_alteracao_apos_abertura
         WHERE dias_apos_publicacao > 30
        """,
    )


def _inserir_redflags_item(con: duckdb.DuckDBPyConnection) -> None:
    item_id = (
        "cd_orgao || '|' || nr_licitacao || '|' || ano_licitacao || '|' || "
        "cd_tipo_modalidade || '|' || nr_lote || '|' || nr_item"
    )
    _insert(
        con,
        "alerta_sobrepreco_alto",
        f"""
        SELECT 'item' AS escopo, {item_id} AS entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               nr_lote, nr_item, cnpj_fornecedor AS cnpj,
               'alerta_sobrepreco_alto' AS sinal,
               'razao_vs_mediana=' || CAST(razao_vs_mediana AS VARCHAR) ||
               '; valor=' || CAST(valor_unitario_homologado AS VARCHAR) ||
               '; mediana=' || CAST(mediana AS VARCHAR) AS evidencia
          FROM vw_sobrepreco_indicios
         WHERE razao_vs_mediana >= 5
        """,
    )
    _insert(
        con,
        "alerta_sobrepreco_moderado",
        f"""
        SELECT 'item' AS escopo, {item_id} AS entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               nr_lote, nr_item, cnpj_fornecedor AS cnpj,
               'alerta_sobrepreco_moderado' AS sinal,
               'razao_vs_mediana=' || CAST(razao_vs_mediana AS VARCHAR) ||
               '; valor=' || CAST(valor_unitario_homologado AS VARCHAR) ||
               '; mediana=' || CAST(mediana AS VARCHAR) AS evidencia
          FROM vw_sobrepreco_indicios
         WHERE razao_vs_mediana >= 3
           AND razao_vs_mediana < 5
        """,
    )
    _insert(
        con,
        "alerta_covid_sobrepreco",
        f"""
        SELECT 'item' AS escopo, {item_id} AS entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               nr_lote, nr_item, cnpj_fornecedor AS cnpj,
               'alerta_covid_sobrepreco' AS sinal,
               'razao_vs_mediana=' || CAST(razao_vs_mediana AS VARCHAR) AS evidencia
          FROM vw_sobrepreco_indicios
         WHERE flag_covid IS TRUE
        """,
    )
    _insert(
        con,
        "indicio_preco_estimado_acima_mediana",
        """
        WITH grupo AS (
            SELECT descricao_normalizada, unidade,
                   MEDIAN(valor_unitario_estimado) AS mediana_estimado,
                   COUNT(*) AS n_obs
              FROM itens
             WHERE descricao_normalizada IS NOT NULL
               AND unidade IS NOT NULL
               AND valor_unitario_estimado IS NOT NULL
               AND valor_unitario_estimado > 0
             GROUP BY 1,2
            HAVING COUNT(*) >= 10
        )
        SELECT 'item' AS escopo,
               i.cd_orgao || '|' || i.nr_licitacao || '|' || i.ano_licitacao ||
               '|' || i.cd_tipo_modalidade || '|' || i.nr_lote || '|' || i.nr_item
               AS entidade_id,
               i.cd_orgao, i.nr_licitacao, i.ano_licitacao, i.cd_tipo_modalidade,
               i.nr_lote, i.nr_item, i.cnpj_fornecedor AS cnpj,
               'indicio_preco_estimado_acima_mediana' AS sinal,
               'razao_vs_mediana_estimado=' ||
               CAST(i.valor_unitario_estimado / g.mediana_estimado AS VARCHAR) ||
               '; estimado=' || CAST(i.valor_unitario_estimado AS VARCHAR) ||
               '; mediana=' || CAST(g.mediana_estimado AS VARCHAR) AS evidencia
          FROM itens i
          JOIN grupo g USING (descricao_normalizada, unidade)
         WHERE i.valor_unitario_estimado / g.mediana_estimado >= 3
        """,
    )
    _insert(
        con,
        "indicio_proposta_item_perdedora_artificialmente_alta",
        """
        WITH rankeadas AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   nr_lote, nr_item, cnpj_proposta, valor_unitario,
                   ROW_NUMBER() OVER (
                       PARTITION BY cd_orgao, nr_licitacao, ano_licitacao,
                                    cd_tipo_modalidade, nr_lote, nr_item
                       ORDER BY valor_unitario ASC
                   ) AS posicao,
                   COUNT(*) OVER (
                       PARTITION BY cd_orgao, nr_licitacao, ano_licitacao,
                                    cd_tipo_modalidade, nr_lote, nr_item
                   ) AS n_propostas
              FROM propostas_itens
             WHERE valor_unitario IS NOT NULL
               AND valor_unitario > 0
        ),
        menor AS (SELECT * FROM rankeadas WHERE posicao = 1),
        segunda AS (SELECT * FROM rankeadas WHERE posicao = 2)
        SELECT 'item' AS escopo,
               m.cd_orgao || '|' || m.nr_licitacao || '|' || m.ano_licitacao ||
               '|' || m.cd_tipo_modalidade || '|' || m.nr_lote || '|' || m.nr_item
               AS entidade_id,
               m.cd_orgao, m.nr_licitacao, m.ano_licitacao, m.cd_tipo_modalidade,
               m.nr_lote, m.nr_item, m.cnpj_proposta AS cnpj,
               'indicio_proposta_item_perdedora_artificialmente_alta' AS sinal,
               'menor=' || CAST(m.valor_unitario AS VARCHAR) ||
               '; segunda=' || CAST(s.valor_unitario AS VARCHAR) ||
               '; razao=' || CAST(s.valor_unitario / m.valor_unitario AS VARCHAR) AS evidencia
          FROM menor m
          JOIN segunda s USING (
              cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade, nr_lote, nr_item
          )
         WHERE m.n_propostas >= 3
           AND s.valor_unitario / m.valor_unitario >= 2
        """,
    )
    _insert(
        con,
        "indicio_desclassificacao_conveniente",
        """
        WITH rankeadas AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   nr_lote, nr_item, cnpj_proposta, valor_unitario,
                   resultado_proposta, resultado_habilitacao,
                   ROW_NUMBER() OVER (
                       PARTITION BY cd_orgao, nr_licitacao, ano_licitacao,
                                    cd_tipo_modalidade, nr_lote, nr_item
                       ORDER BY valor_unitario ASC
                   ) AS posicao
              FROM propostas_itens
             WHERE valor_unitario IS NOT NULL
               AND valor_unitario > 0
        ),
        menor AS (SELECT * FROM rankeadas WHERE posicao = 1),
        classificada AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   nr_lote, nr_item, MIN(valor_unitario) AS menor_classificada
              FROM rankeadas
             WHERE resultado_proposta = 'C'
             GROUP BY 1,2,3,4,5,6
        )
        SELECT 'item' AS escopo,
               m.cd_orgao || '|' || m.nr_licitacao || '|' || m.ano_licitacao ||
               '|' || m.cd_tipo_modalidade || '|' || m.nr_lote || '|' || m.nr_item
               AS entidade_id,
               m.cd_orgao, m.nr_licitacao, m.ano_licitacao, m.cd_tipo_modalidade,
               m.nr_lote, m.nr_item, m.cnpj_proposta AS cnpj,
               'indicio_desclassificacao_conveniente' AS sinal,
               'menor_desclassificada=' || CAST(m.valor_unitario AS VARCHAR) ||
               '; menor_classificada=' || CAST(c.menor_classificada AS VARCHAR) ||
               '; resultado=' || COALESCE(m.resultado_proposta, '?') ||
               '/' || COALESCE(m.resultado_habilitacao, '?') AS evidencia
          FROM menor m
          JOIN classificada c USING (
              cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade, nr_lote, nr_item
          )
         WHERE COALESCE(m.resultado_proposta, '') <> 'C'
           AND c.menor_classificada > m.valor_unitario
        """,
    )


def _criar_scores_agregados(
    con: duckdb.DuckDBPyConnection,
    limiar_possivel_fraude: int,
) -> None:
    for nome in (
        "scores_fornecedor",
        "scores_licitacao",
        "scores_item",
        "vw_possivel_fraude",
    ):
        con.execute(f"DROP VIEW IF EXISTS {nome}")
        con.execute(f"DROP TABLE IF EXISTS {nome}")

    con.execute(
        f"""
        CREATE TABLE scores_fornecedor AS
        SELECT entidade_id AS cnpj,
               SUM(pontos)::INTEGER AS score_bruto,
               LEAST(SUM(pontos), 100)::INTEGER AS score,
               SUM(pontos) >= {limiar_possivel_fraude} AS possivel_fraude,
               COUNT(*)::INTEGER AS qtd_sinais,
               STRING_AGG(DISTINCT sinal, ', ' ORDER BY sinal) AS sinais
          FROM redflag_eventos
         WHERE escopo = 'fornecedor'
         GROUP BY entidade_id
        """
    )
    con.execute(
        f"""
        CREATE TABLE scores_licitacao AS
        SELECT entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               SUM(pontos)::INTEGER AS score_bruto,
               LEAST(SUM(pontos), 100)::INTEGER AS score,
               SUM(pontos) >= {limiar_possivel_fraude} AS possivel_fraude,
               COUNT(*)::INTEGER AS qtd_sinais,
               STRING_AGG(DISTINCT sinal, ', ' ORDER BY sinal) AS sinais
          FROM redflag_eventos
         WHERE escopo = 'licitacao'
         GROUP BY entidade_id, cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade
        """
    )
    con.execute(
        f"""
        CREATE TABLE scores_item AS
        SELECT entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               nr_lote, nr_item, cnpj,
               SUM(pontos)::INTEGER AS score_bruto,
               LEAST(SUM(pontos), 100)::INTEGER AS score,
               SUM(pontos) >= {limiar_possivel_fraude} AS possivel_fraude,
               COUNT(*)::INTEGER AS qtd_sinais,
               STRING_AGG(DISTINCT sinal, ', ' ORDER BY sinal) AS sinais
          FROM redflag_eventos
         WHERE escopo = 'item'
         GROUP BY entidade_id, cd_orgao, nr_licitacao, ano_licitacao,
                  cd_tipo_modalidade, nr_lote, nr_item, cnpj
        """
    )
    con.execute(
        """
        CREATE VIEW vw_possivel_fraude AS
        SELECT 'fornecedor' AS escopo, cnpj AS entidade_id, score_bruto, score,
               qtd_sinais, sinais
          FROM scores_fornecedor
         WHERE possivel_fraude
        UNION ALL
        SELECT 'licitacao' AS escopo, entidade_id, score_bruto, score, qtd_sinais, sinais
          FROM scores_licitacao
         WHERE possivel_fraude
        UNION ALL
        SELECT 'item' AS escopo, entidade_id, score_bruto, score, qtd_sinais, sinais
          FROM scores_item
         WHERE possivel_fraude
        """
    )

    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_redflag_eventos_entidade "
        "ON redflag_eventos (escopo, entidade_id)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_scores_fornecedor_score "
        "ON scores_fornecedor (score_bruto)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_scores_licitacao_score "
        "ON scores_licitacao (score_bruto)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_scores_item_score "
        "ON scores_item (score_bruto)"
    )
