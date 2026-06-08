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
    "indicio_socio_comum_competidores": {
        "pontos": 22,
        "forca": "Forte",
        "escopo": "fornecedor",
        "descricao": "Empresas concorrentes na mesma licitacao compartilham socio mascarado.",
    },
    "indicio_endereco_compartilhado_competidores": {
        "pontos": 12,
        "forca": "Media",
        "escopo": "fornecedor",
        "descricao": "Empresas concorrentes na mesma licitacao compartilham endereco cadastral.",
    },
    "indicio_rotacao_vencedores": {
        "pontos": 20,
        "forca": "Forte",
        "escopo": "fornecedor",
        "descricao": "Par de competidores frequentes alterna vitorias entre licitacoes.",
    },
    "indicio_fornecedor_concentrado_por_orgao": {
        "pontos": 12,
        "forca": "Media",
        "escopo": "fornecedor",
        "descricao": "Fornecedor concentra valor relevante de contratos em um unico orgao.",
    },
    "indicio_fornecedor_exclusivo_orgao": {
        "pontos": 10,
        "forca": "Media",
        "escopo": "fornecedor",
        "descricao": "Fornecedor recebe praticamente todos os contratos de um unico orgao.",
    },
    "alerta_competicao_zero": {
        "pontos": 22,
        "forca": "Forte",
        "escopo": "licitacao",
        "descricao": "Licitacao tem exatamente uma proposta classificada.",
    },
    "alerta_baixa_competicao": {
        "pontos": 6,
        "forca": "Fraca/contextual",
        "escopo": "licitacao",
        "descricao": "Licitacao tem ate dois participantes ou propostas classificadas.",
    },
    "alerta_cover_bidding": {
        "pontos": 15,
        "forca": "Media",
        "escopo": "licitacao",
        "descricao": "Segunda menor proposta e pelo menos 2 vezes a menor proposta.",
    },
    "alerta_dispensa_alto_valor": {
        "pontos": 25,
        "forca": "Forte",
        "escopo": "licitacao",
        "descricao": "Dispensa ou inexigibilidade com valor acima do limiar operacional.",
    },
    "indicio_fracionamento_dispensa": {
        "pontos": 25,
        "forca": "Forte",
        "escopo": "licitacao",
        "descricao": "Dispensas similares e repetidas somam valor alto em janela curta.",
    },
    "indicio_vencedor_recorrente_mesmo_objeto": {
        "pontos": 15,
        "forca": "Media",
        "escopo": "licitacao",
        "descricao": "Mesmo fornecedor vence repetidamente objeto parecido no mesmo orgao.",
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
    "indicio_desconto_inexistente_em_ambiente_competitivo": {
        "pontos": 8,
        "forca": "Fraca/contextual",
        "escopo": "licitacao",
        "descricao": "Proposta vencedora quase nao oferece desconto apesar de competicao.",
    },
    "alerta_alteracao_regra_tardia": {
        "pontos": 10,
        "forca": "Media",
        "escopo": "licitacao",
        "descricao": "Alteracao ou republicacao ocorre mais de 30 dias apos a primeira publicacao.",
    },
    "indicio_alteracao_edital_beneficia_vencedor": {
        "pontos": 20,
        "forca": "Forte",
        "escopo": "licitacao",
        "descricao": "Vencedor apresenta proposta apos alteracao ou republicacao do edital.",
    },
    "alerta_anulacao_historica": {
        "pontos": 5,
        "forca": "Fraca/contextual",
        "escopo": "licitacao",
        "descricao": "Orgao tem historico recorrente de anulacoes ou suspensoes.",
    },
    "indicio_prazo_curto_publicacao_abertura": {
        "pontos": 15,
        "forca": "Media",
        "escopo": "licitacao",
        "descricao": "Primeira proposta ocorre poucos dias apos publicacao do edital.",
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
    "indicio_fonte_referencia_ausente_preco_alto": {
        "pontos": 8,
        "forca": "Fraca/contextual",
        "escopo": "item",
        "automatico": False,
        "descricao": (
            "Item com preco alto nao informa fonte de referencia; depende de "
            "colunas ainda nao preservadas em itens."
        ),
    },
    "alerta_orcamento_sigiloso_baixa_competicao": {
        "pontos": 8,
        "forca": "Fraca/contextual",
        "escopo": "licitacao",
        "automatico": False,
        "descricao": (
            "Orcamento sigiloso combinado com baixa competicao; depende de "
            "coluna ainda nao preservada no banco analitico."
        ),
    },
    "llm_justificativa_inexigibilidade_fraca": {
        "pontos": 20,
        "forca": "LLM/textual forte",
        "escopo": "llm",
        "automatico": False,
        "descricao": "Avaliacao textual de justificativa fraca para dispensa/inexigibilidade.",
    },
    "llm_objeto_vago_ou_direcionado": {
        "pontos": 12,
        "forca": "LLM/textual media",
        "escopo": "llm",
        "automatico": False,
        "descricao": "Avaliacao textual de objeto vago, generico ou direcionado.",
    },
    "llm_cnae_incompativel_objeto": {
        "pontos": 15,
        "forca": "LLM/textual media",
        "escopo": "llm",
        "automatico": False,
        "descricao": "Avaliacao textual de compatibilidade entre CNAE, objeto e itens.",
    },
    "llm_fracionamento_semantico_objetos": {
        "pontos": 20,
        "forca": "LLM/textual forte",
        "escopo": "llm",
        "automatico": False,
        "descricao": "Avaliacao semantica de objetos similares em processos distintos.",
    },
    "llm_alteracao_edital_direcionadora": {
        "pontos": 18,
        "forca": "LLM/textual forte",
        "escopo": "llm",
        "automatico": False,
        "descricao": "Avaliacao textual de alteracao de edital potencialmente direcionadora.",
    },
    "llm_impugnacao_indica_restricao": {
        "pontos": 15,
        "forca": "LLM/textual media",
        "escopo": "llm",
        "automatico": False,
        "descricao": "Avaliacao textual de impugnacoes ou esclarecimentos restritivos.",
    },
    "llm_item_generico_incomparavel": {
        "pontos": 0,
        "forca": "Controle de qualidade",
        "escopo": "llm",
        "automatico": False,
        "descricao": "Controle textual para bloquear ou reduzir comparacoes ruins de sobrepreco.",
    },
    "llm_preco_plausivel_pelo_contexto": {
        "pontos": 0,
        "forca": "LLM/textual contextual",
        "escopo": "llm",
        "automatico": False,
        "descricao": "Avaliacao contextual de plausibilidade de preco aparentemente alto.",
    },
    "llm_texto_copiado_entre_editais": {
        "pontos": 8,
        "forca": "LLM/textual contextual",
        "escopo": "llm",
        "automatico": False,
        "descricao": "Avaliacao textual de alta semelhanca entre editais ou justificativas.",
    },
    "indicio_orgao_sobrepreco_recorrente": {
        "pontos": 12,
        "forca": "Media",
        "escopo": "orgao",
        "descricao": "Orgao aparece recorrentemente em itens com indicio de sobrepreco.",
    },
    "indicio_orgao_baixa_competicao_recorrente": {
        "pontos": 10,
        "forca": "Media",
        "escopo": "orgao",
        "descricao": "Orgao tem recorrencia de licitacoes com baixa competicao.",
    },
    "indicio_orgao_dispensas_recorrentes": {
        "pontos": 12,
        "forca": "Media",
        "escopo": "orgao",
        "descricao": "Orgao usa dispensa ou inexigibilidade de forma recorrente.",
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
    _inserir_redflags_orgao(con)
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
    _insert(
        con,
        "indicio_socio_comum_competidores",
        """
        WITH competidores AS (
            SELECT DISTINCT cd_orgao, nr_licitacao, ano_licitacao,
                   cd_tipo_modalidade, cnpj_proposta
              FROM propostas
             WHERE cnpj_proposta IS NOT NULL
        ),
        pares AS (
            SELECT c1.cd_orgao, c1.nr_licitacao, c1.ano_licitacao,
                   c1.cd_tipo_modalidade,
                   c1.cnpj_proposta AS cnpj_a,
                   c2.cnpj_proposta AS cnpj_b,
                   s1.doc_socio
              FROM competidores c1
              JOIN competidores c2
                ON c1.cd_orgao = c2.cd_orgao
               AND c1.nr_licitacao = c2.nr_licitacao
               AND c1.ano_licitacao = c2.ano_licitacao
               AND c1.cd_tipo_modalidade = c2.cd_tipo_modalidade
               AND c1.cnpj_proposta < c2.cnpj_proposta
              JOIN socios s1 ON s1.cnpj = c1.cnpj_proposta
              JOIN socios s2 ON s2.cnpj = c2.cnpj_proposta
                           AND s2.doc_socio = s1.doc_socio
             WHERE s1.doc_socio IS NOT NULL
        )
        SELECT 'fornecedor' AS escopo,
               cnpj AS entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, cnpj,
               'indicio_socio_comum_competidores' AS sinal,
               'doc_socio=' || doc_socio ||
               '; competidor=' || competidor AS evidencia
          FROM (
              SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                     cnpj_a AS cnpj, cnpj_b AS competidor, doc_socio
                FROM pares
              UNION ALL
              SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                     cnpj_b AS cnpj, cnpj_a AS competidor, doc_socio
                FROM pares
          ) t
        """,
    )
    _insert(
        con,
        "indicio_endereco_compartilhado_competidores",
        """
        WITH competidores AS (
            SELECT DISTINCT cd_orgao, nr_licitacao, ano_licitacao,
                   cd_tipo_modalidade, cnpj_proposta
              FROM propostas
             WHERE cnpj_proposta IS NOT NULL
        ),
        pares AS (
            SELECT c1.cd_orgao, c1.nr_licitacao, c1.ano_licitacao,
                   c1.cd_tipo_modalidade,
                   c1.cnpj_proposta AS cnpj_a,
                   c2.cnpj_proposta AS cnpj_b,
                   e1.endereco
              FROM competidores c1
              JOIN competidores c2
                ON c1.cd_orgao = c2.cd_orgao
               AND c1.nr_licitacao = c2.nr_licitacao
               AND c1.ano_licitacao = c2.ano_licitacao
               AND c1.cd_tipo_modalidade = c2.cd_tipo_modalidade
               AND c1.cnpj_proposta < c2.cnpj_proposta
              JOIN empresas e1 ON e1.cnpj = c1.cnpj_proposta
              JOIN empresas e2 ON e2.cnpj = c2.cnpj_proposta
                            AND TRIM(UPPER(e2.endereco)) = TRIM(UPPER(e1.endereco))
             WHERE e1.endereco IS NOT NULL
               AND LENGTH(TRIM(e1.endereco)) >= 12
        )
        SELECT 'fornecedor' AS escopo,
               cnpj AS entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, cnpj,
               'indicio_endereco_compartilhado_competidores' AS sinal,
               'endereco=' || endereco ||
               '; competidor=' || competidor AS evidencia
          FROM (
              SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                     cnpj_a AS cnpj, cnpj_b AS competidor, endereco
                FROM pares
              UNION ALL
              SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                     cnpj_b AS cnpj, cnpj_a AS competidor, endereco
                FROM pares
          ) t
        """,
    )
    _insert(
        con,
        "indicio_rotacao_vencedores",
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
               AND cnpj_proposta IS NOT NULL
               AND valor_total_proposta IS NOT NULL
               AND valor_total_proposta > 0
        ),
        pares AS (
            SELECT r1.cnpj_proposta AS cnpj_a,
                   r2.cnpj_proposta AS cnpj_b,
                   COUNT(*) AS licitacoes_juntas,
                   SUM(CASE WHEN r1.posicao = 1 THEN 1 ELSE 0 END) AS vitorias_a,
                   SUM(CASE WHEN r2.posicao = 1 THEN 1 ELSE 0 END) AS vitorias_b
              FROM rankeadas r1
              JOIN rankeadas r2
                ON r1.cd_orgao = r2.cd_orgao
               AND r1.nr_licitacao = r2.nr_licitacao
               AND r1.ano_licitacao = r2.ano_licitacao
               AND r1.cd_tipo_modalidade = r2.cd_tipo_modalidade
               AND r1.cnpj_proposta < r2.cnpj_proposta
             GROUP BY 1,2
            HAVING COUNT(*) >= 5
               AND SUM(CASE WHEN r1.posicao = 1 THEN 1 ELSE 0 END) >= 1
               AND SUM(CASE WHEN r2.posicao = 1 THEN 1 ELSE 0 END) >= 1
        )
        SELECT DISTINCT 'fornecedor' AS escopo,
               r.cnpj_proposta AS entidade_id,
               r.cd_orgao, r.nr_licitacao, r.ano_licitacao, r.cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, r.cnpj_proposta AS cnpj,
               'indicio_rotacao_vencedores' AS sinal,
               'par=' || p.cnpj_a || '/' || p.cnpj_b ||
               '; licitacoes_juntas=' || CAST(p.licitacoes_juntas AS VARCHAR) ||
               '; vitorias=' || CAST(p.vitorias_a AS VARCHAR) ||
               '/' || CAST(p.vitorias_b AS VARCHAR) AS evidencia
          FROM rankeadas r
          JOIN pares p
            ON r.cnpj_proposta IN (p.cnpj_a, p.cnpj_b)
         WHERE r.posicao = 1
        """,
    )
    _insert(
        con,
        "indicio_fornecedor_concentrado_por_orgao",
        """
        WITH totais AS (
            SELECT cnpj_fornecedor, orgao,
                   COUNT(*) AS qtd_contratos_orgao,
                   SUM(valor_contrato) AS valor_orgao,
                   SUM(SUM(valor_contrato)) OVER (PARTITION BY cnpj_fornecedor)
                       AS valor_total
              FROM contratos
             WHERE cnpj_fornecedor IS NOT NULL
               AND orgao IS NOT NULL
               AND valor_contrato IS NOT NULL
             GROUP BY 1,2
        )
        SELECT 'fornecedor' AS escopo,
               cnpj_fornecedor AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               NULL AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               cnpj_fornecedor AS cnpj,
               'indicio_fornecedor_concentrado_por_orgao' AS sinal,
               'orgao=' || orgao ||
               '; valor_orgao=' || CAST(valor_orgao AS VARCHAR) ||
               '; valor_total=' || CAST(valor_total AS VARCHAR) AS evidencia
          FROM totais
         WHERE valor_total >= 100000
           AND qtd_contratos_orgao >= 3
           AND valor_orgao / valor_total >= 0.80
        """,
    )
    _insert(
        con,
        "indicio_fornecedor_exclusivo_orgao",
        """
        WITH totais AS (
            SELECT cnpj_fornecedor, orgao,
                   COUNT(*) AS qtd_contratos_orgao,
                   SUM(valor_contrato) AS valor_orgao,
                   SUM(SUM(valor_contrato)) OVER (PARTITION BY cnpj_fornecedor)
                       AS valor_total
              FROM contratos
             WHERE cnpj_fornecedor IS NOT NULL
               AND orgao IS NOT NULL
               AND valor_contrato IS NOT NULL
             GROUP BY 1,2
        )
        SELECT 'fornecedor' AS escopo,
               cnpj_fornecedor AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               NULL AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               cnpj_fornecedor AS cnpj,
               'indicio_fornecedor_exclusivo_orgao' AS sinal,
               'orgao=' || orgao ||
               '; valor_orgao=' || CAST(valor_orgao AS VARCHAR) ||
               '; valor_total=' || CAST(valor_total AS VARCHAR) AS evidencia
         FROM totais
         WHERE valor_total >= 50000
           AND qtd_contratos_orgao >= 3
           AND valor_orgao / valor_total >= 0.95
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
        "alerta_baixa_competicao",
        f"""
        WITH por_propostas AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   COUNT(DISTINCT cnpj_proposta) AS qtd_participantes
              FROM propostas
             WHERE cnpj_proposta IS NOT NULL
             GROUP BY 1,2,3,4
        )
        SELECT 'licitacao' AS escopo, {lic_id} AS entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, NULL AS cnpj,
               'alerta_baixa_competicao' AS sinal,
               'qtd_participantes=' || CAST(qtd_participantes AS VARCHAR) AS evidencia
          FROM por_propostas
         WHERE qtd_participantes BETWEEN 1 AND 2
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
        "alerta_dispensa_alto_valor",
        """
        SELECT 'licitacao' AS escopo,
               orgao || '|' || modalidade || '|' ||
               COALESCE(CAST(data_contrato AS VARCHAR), '?') || '|' ||
               COALESCE(numero_contrato, '?') AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               modalidade AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               cnpj_fornecedor AS cnpj,
               'alerta_dispensa_alto_valor' AS sinal,
               'modalidade=' || COALESCE(modalidade, '?') ||
               '; valor=' || CAST(valor_contrato AS VARCHAR) ||
               '; orgao=' || COALESCE(orgao, '?') AS evidencia
          FROM contratos
         WHERE modalidade IN ('DSP', 'INX')
           AND valor_contrato >= 100000
        """,
    )
    _insert(
        con,
        "indicio_fracionamento_dispensa",
        """
        WITH grupos AS (
            SELECT orgao, cnpj_fornecedor, objeto, modalidade,
                   DATE_TRUNC('quarter', data_contrato) AS janela,
                   COUNT(*) AS qtd_contratos,
                   SUM(valor_contrato) AS valor_total
              FROM contratos
             WHERE modalidade IN ('DSP', 'INX')
               AND orgao IS NOT NULL
               AND cnpj_fornecedor IS NOT NULL
               AND objeto IS NOT NULL
               AND data_contrato IS NOT NULL
               AND valor_contrato IS NOT NULL
               AND valor_contrato < 100000
             GROUP BY 1,2,3,4,5
            HAVING COUNT(*) >= 2
               AND SUM(valor_contrato) >= 100000
        )
        SELECT 'licitacao' AS escopo,
               c.orgao || '|' || c.modalidade || '|' ||
               COALESCE(CAST(c.data_contrato AS VARCHAR), '?') || '|' ||
               COALESCE(c.numero_contrato, '?') AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               c.modalidade AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               c.cnpj_fornecedor AS cnpj,
               'indicio_fracionamento_dispensa' AS sinal,
               'grupo=' || COALESCE(c.objeto, '?') ||
               '; janela=' || CAST(g.janela AS VARCHAR) ||
               '; qtd=' || CAST(g.qtd_contratos AS VARCHAR) ||
               '; soma=' || CAST(g.valor_total AS VARCHAR) AS evidencia
          FROM contratos c
          JOIN grupos g
            ON c.orgao = g.orgao
           AND c.cnpj_fornecedor = g.cnpj_fornecedor
           AND c.objeto = g.objeto
           AND c.modalidade = g.modalidade
           AND DATE_TRUNC('quarter', c.data_contrato) = g.janela
        """,
    )
    _insert(
        con,
        "indicio_vencedor_recorrente_mesmo_objeto",
        """
        WITH grupos AS (
            SELECT orgao, cnpj_fornecedor, objeto,
                   COUNT(*) AS qtd_contratos,
                   SUM(valor_contrato) AS valor_total
              FROM contratos
             WHERE orgao IS NOT NULL
               AND cnpj_fornecedor IS NOT NULL
               AND objeto IS NOT NULL
               AND valor_contrato IS NOT NULL
             GROUP BY 1,2,3
            HAVING COUNT(*) >= 3
               AND SUM(valor_contrato) >= 100000
        )
        SELECT 'licitacao' AS escopo,
               c.orgao || '|' || COALESCE(c.modalidade, '?') || '|' ||
               COALESCE(CAST(c.data_contrato AS VARCHAR), '?') || '|' ||
               COALESCE(c.numero_contrato, '?') AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               c.modalidade AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               c.cnpj_fornecedor AS cnpj,
               'indicio_vencedor_recorrente_mesmo_objeto' AS sinal,
               'orgao=' || c.orgao ||
               '; objeto=' || c.objeto ||
               '; qtd=' || CAST(g.qtd_contratos AS VARCHAR) ||
               '; valor_total=' || CAST(g.valor_total AS VARCHAR) AS evidencia
          FROM contratos c
          JOIN grupos g
            ON c.orgao = g.orgao
           AND c.cnpj_fornecedor = g.cnpj_fornecedor
           AND c.objeto = g.objeto
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
        "indicio_desconto_inexistente_em_ambiente_competitivo",
        f"""
        WITH stats AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   COUNT(*) AS n_classificadas,
                   MIN(percentual_desconto) AS menor_desconto
              FROM propostas
             WHERE resultado_proposta = 'C'
               AND valor_total_proposta IS NOT NULL
             GROUP BY 1,2,3,4
        )
        SELECT 'licitacao' AS escopo, {lic_id} AS entidade_id,
               cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, NULL AS cnpj,
               'indicio_desconto_inexistente_em_ambiente_competitivo' AS sinal,
               'n_classificadas=' || CAST(n_classificadas AS VARCHAR) ||
               '; menor_desconto=' || COALESCE(CAST(menor_desconto AS VARCHAR), '?')
               AS evidencia
          FROM stats
         WHERE n_classificadas >= 3
           AND COALESCE(menor_desconto, 0) <= 0
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
    _insert(
        con,
        "indicio_alteracao_edital_beneficia_vencedor",
        """
        WITH alteracoes AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   MAX(data_evento) AS ultima_alteracao
              FROM eventos_licitacao
             WHERE cd_tipo_evento IN ('AED', 'REE')
               AND data_evento IS NOT NULL
             GROUP BY 1,2,3,4
        ),
        vencedoras AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   cnpj_proposta, data_proposta, valor_total_proposta,
                   ROW_NUMBER() OVER (
                       PARTITION BY cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade
                       ORDER BY valor_total_proposta ASC
                   ) AS posicao
              FROM propostas
             WHERE resultado_proposta = 'C'
               AND valor_total_proposta IS NOT NULL
               AND valor_total_proposta > 0
        )
        SELECT 'licitacao' AS escopo,
               v.cd_orgao || '|' || v.nr_licitacao || '|' || v.ano_licitacao ||
               '|' || v.cd_tipo_modalidade AS entidade_id,
               v.cd_orgao, v.nr_licitacao, v.ano_licitacao, v.cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, v.cnpj_proposta AS cnpj,
               'indicio_alteracao_edital_beneficia_vencedor' AS sinal,
               'ultima_alteracao=' || CAST(a.ultima_alteracao AS VARCHAR) ||
               '; data_proposta=' || CAST(v.data_proposta AS VARCHAR) ||
               '; vencedora=' || v.cnpj_proposta AS evidencia
          FROM vencedoras v
          JOIN alteracoes a USING (
              cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade
          )
         WHERE v.posicao = 1
           AND v.data_proposta IS NOT NULL
           AND v.data_proposta >= a.ultima_alteracao
        """,
    )
    _insert(
        con,
        "alerta_anulacao_historica",
        """
        WITH orgaos AS (
            SELECT cd_orgao,
                   COUNT(*) AS qtd_eventos
              FROM eventos_licitacao
             WHERE cd_tipo_evento IN ('ANO', 'SUO')
             GROUP BY 1
            HAVING COUNT(*) >= 5
        )
        SELECT DISTINCT 'licitacao' AS escopo,
               e.cd_orgao || '|' || e.nr_licitacao || '|' || e.ano_licitacao ||
               '|' || e.cd_tipo_modalidade AS entidade_id,
               e.cd_orgao, e.nr_licitacao, e.ano_licitacao, e.cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, NULL AS cnpj,
               'alerta_anulacao_historica' AS sinal,
               'cd_orgao=' || e.cd_orgao ||
               '; anulacoes_suspensoes=' || CAST(o.qtd_eventos AS VARCHAR) AS evidencia
          FROM eventos_licitacao e
          JOIN orgaos o USING (cd_orgao)
        """,
    )
    _insert(
        con,
        "indicio_prazo_curto_publicacao_abertura",
        """
        WITH publicacao AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   MIN(data_evento) AS data_publicacao
              FROM eventos_licitacao
             WHERE cd_tipo_evento IN ('PUE', 'PUB')
               AND data_evento IS NOT NULL
             GROUP BY 1,2,3,4
        ),
        primeira_proposta AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   MIN(data_proposta) AS data_primeira_proposta
              FROM propostas
             WHERE data_proposta IS NOT NULL
             GROUP BY 1,2,3,4
        )
        SELECT 'licitacao' AS escopo,
               p.cd_orgao || '|' || p.nr_licitacao || '|' || p.ano_licitacao ||
               '|' || p.cd_tipo_modalidade AS entidade_id,
               p.cd_orgao, p.nr_licitacao, p.ano_licitacao, p.cd_tipo_modalidade,
               NULL AS nr_lote, NULL AS nr_item, NULL AS cnpj,
               'indicio_prazo_curto_publicacao_abertura' AS sinal,
               'publicacao=' || CAST(p.data_publicacao AS VARCHAR) ||
               '; primeira_proposta=' || CAST(pp.data_primeira_proposta AS VARCHAR) ||
               '; dias=' || CAST(pp.data_primeira_proposta - p.data_publicacao AS VARCHAR)
               AS evidencia
          FROM publicacao p
          JOIN primeira_proposta pp USING (
              cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade
          )
         WHERE pp.data_primeira_proposta >= p.data_publicacao
           AND pp.data_primeira_proposta - p.data_publicacao <= 3
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


def _inserir_redflags_orgao(con: duckdb.DuckDBPyConnection) -> None:
    _insert(
        con,
        "indicio_orgao_sobrepreco_recorrente",
        """
        WITH orgaos AS (
            SELECT cd_orgao,
                   COUNT(*) AS qtd_indicios,
                   AVG(razao_vs_mediana) AS razao_media,
                   MAX(razao_vs_mediana) AS razao_pico
              FROM vw_sobrepreco_indicios
             WHERE cd_orgao IS NOT NULL
             GROUP BY 1
            HAVING COUNT(*) >= 10
               AND AVG(razao_vs_mediana) >= 3
        )
        SELECT 'orgao' AS escopo,
               cd_orgao AS entidade_id,
               cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               NULL AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               NULL AS cnpj,
               'indicio_orgao_sobrepreco_recorrente' AS sinal,
               'qtd_indicios=' || CAST(qtd_indicios AS VARCHAR) ||
               '; razao_media=' || CAST(razao_media AS VARCHAR) ||
               '; razao_pico=' || CAST(razao_pico AS VARCHAR) AS evidencia
          FROM orgaos
        """,
    )
    _insert(
        con,
        "indicio_orgao_baixa_competicao_recorrente",
        """
        WITH licitacoes AS (
            SELECT cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade,
                   COUNT(DISTINCT cnpj_proposta) AS qtd_participantes
              FROM propostas
             WHERE cd_orgao IS NOT NULL
               AND cnpj_proposta IS NOT NULL
             GROUP BY 1,2,3,4
        ),
        orgaos AS (
            SELECT cd_orgao,
                   COUNT(*) AS qtd_licitacoes,
                   SUM(CASE WHEN qtd_participantes <= 2 THEN 1 ELSE 0 END)
                       AS qtd_baixa_competicao
              FROM licitacoes
             GROUP BY 1
            HAVING COUNT(*) >= 10
               AND SUM(CASE WHEN qtd_participantes <= 2 THEN 1 ELSE 0 END)
                   / COUNT(*) >= 0.50
        )
        SELECT 'orgao' AS escopo,
               cd_orgao AS entidade_id,
               cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               NULL AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               NULL AS cnpj,
               'indicio_orgao_baixa_competicao_recorrente' AS sinal,
               'qtd_baixa_competicao=' || CAST(qtd_baixa_competicao AS VARCHAR) ||
               '; qtd_licitacoes=' || CAST(qtd_licitacoes AS VARCHAR) AS evidencia
          FROM orgaos
        """,
    )
    _insert(
        con,
        "indicio_orgao_dispensas_recorrentes",
        """
        WITH orgaos AS (
            SELECT orgao,
                   COUNT(*) AS qtd_contratos,
                   SUM(CASE WHEN modalidade IN ('DSP', 'INX') THEN 1 ELSE 0 END)
                       AS qtd_dispensas,
                   SUM(CASE WHEN modalidade IN ('DSP', 'INX')
                            THEN COALESCE(valor_contrato, 0) ELSE 0 END)
                       AS valor_dispensas
              FROM contratos
             WHERE orgao IS NOT NULL
             GROUP BY 1
            HAVING COUNT(*) >= 10
               AND SUM(CASE WHEN modalidade IN ('DSP', 'INX') THEN 1 ELSE 0 END)
                   / COUNT(*) >= 0.50
        )
        SELECT 'orgao' AS escopo,
               orgao AS entidade_id,
               NULL AS cd_orgao, NULL AS nr_licitacao, NULL AS ano_licitacao,
               NULL AS cd_tipo_modalidade, NULL AS nr_lote, NULL AS nr_item,
               NULL AS cnpj,
               'indicio_orgao_dispensas_recorrentes' AS sinal,
               'qtd_dispensas=' || CAST(qtd_dispensas AS VARCHAR) ||
               '; qtd_contratos=' || CAST(qtd_contratos AS VARCHAR) ||
               '; valor_dispensas=' || CAST(valor_dispensas AS VARCHAR) AS evidencia
          FROM orgaos
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
        "scores_orgao",
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
        f"""
        CREATE TABLE scores_orgao AS
        SELECT entidade_id AS orgao_id,
               SUM(pontos)::INTEGER AS score_bruto,
               LEAST(SUM(pontos), 100)::INTEGER AS score,
               SUM(pontos) >= {limiar_possivel_fraude} AS possivel_fraude,
               COUNT(*)::INTEGER AS qtd_sinais,
               STRING_AGG(DISTINCT sinal, ', ' ORDER BY sinal) AS sinais
          FROM redflag_eventos
         WHERE escopo = 'orgao'
         GROUP BY entidade_id
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
        UNION ALL
        SELECT 'orgao' AS escopo, orgao_id AS entidade_id, score_bruto, score,
               qtd_sinais, sinais
          FROM scores_orgao
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
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_scores_orgao_score "
        "ON scores_orgao (score_bruto)"
    )
