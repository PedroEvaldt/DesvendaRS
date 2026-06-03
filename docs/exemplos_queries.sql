-- Exemplos de consulta sobre db/dados.duckdb
--
-- Lembrete: este banco levanta INDÍCIOS, não acusações. Padrão estranho pode ter
-- explicação legítima — toda análise precisa de leitura humana posterior.
--
-- Para abrir interativamente:  duckdb db/dados.duckdb

------------------------------------------------------------------
-- 0. Visão geral
------------------------------------------------------------------

SELECT 'contratos' AS tabela, COUNT(*) AS linhas FROM contratos UNION ALL
SELECT 'empresas',  COUNT(*)                     FROM empresas  UNION ALL
SELECT 'socios',    COUNT(*)                     FROM socios    UNION ALL
SELECT 'sancoes',   COUNT(*)                     FROM sancoes;

------------------------------------------------------------------
-- 1. Top 20 fornecedores por valor homologado no RS
------------------------------------------------------------------

SELECT cnpj_fornecedor,
       razao_social,
       COUNT(*)                       AS qtd_contratos,
       SUM(valor_contrato)            AS valor_total,
       COUNT(DISTINCT orgao)          AS orgaos_distintos
  FROM vw_contratos_homologados
 GROUP BY cnpj_fornecedor, razao_social
 ORDER BY valor_total DESC
 LIMIT 20;

------------------------------------------------------------------
-- 2. Fornecedores com contrato ativo E em alguma lista de sanção
--    (CEIS = lista negra federal, CNEP = anticorrupção, CFIL = estado RS)
------------------------------------------------------------------

SELECT c.cnpj_fornecedor,
       c.razao_social,
       c.orgao,
       c.municipio,
       c.valor_contrato,
       c.data_contrato,
       s.tipo_sancao,
       s.fonte AS lista_sancao,
       s.data_inicio AS sancao_inicio,
       s.data_fim    AS sancao_fim
  FROM vw_contratos_homologados c
  JOIN sancoes s ON c.cnpj_fornecedor = s.cnpj
 WHERE c.data_contrato BETWEEN COALESCE(s.data_inicio, DATE '1900-01-01')
                           AND COALESCE(s.data_fim,    DATE '2100-12-31')
 ORDER BY c.valor_contrato DESC NULLS LAST
 LIMIT 100;

------------------------------------------------------------------
-- 3. Indício de baixa competição: licitações com 1 único participante
------------------------------------------------------------------

SELECT municipio,
       orgao,
       COUNT(*)            AS qtd_contratos_unico_participante,
       SUM(valor_contrato) AS valor_total
  FROM vw_contratos_homologados
 WHERE qtd_participantes = 1
 GROUP BY municipio, orgao
 ORDER BY valor_total DESC NULLS LAST
 LIMIT 30;

------------------------------------------------------------------
-- 4. Empresas muito novas que já receberam contratos grandes
--    (recém-abertas + valor alto = vale uma checagem)
------------------------------------------------------------------

SELECT c.cnpj_fornecedor,
       c.razao_social,
       e.data_abertura,
       (c.data_contrato - e.data_abertura) / 30 AS meses_desde_abertura,
       c.valor_contrato,
       c.orgao,
       c.municipio
  FROM vw_contratos_homologados c
  JOIN empresas e ON c.cnpj_fornecedor = e.cnpj
 WHERE e.data_abertura IS NOT NULL
   AND c.data_contrato IS NOT NULL
   AND (c.data_contrato - e.data_abertura) < 180   -- menos de 6 meses
   AND c.valor_contrato > 100000
 ORDER BY c.valor_contrato DESC
 LIMIT 50;

------------------------------------------------------------------
-- 5. Sócios em comum entre fornecedores diferentes
--    (pode indicar grupo econômico não declarado / direcionamento)
------------------------------------------------------------------

SELECT s1.doc_socio,
       s1.nome_socio,
       COUNT(DISTINCT s1.cnpj) AS qtd_empresas
  FROM socios s1
  JOIN contratos c ON c.cnpj_fornecedor = s1.cnpj
 WHERE s1.doc_socio IS NOT NULL
 GROUP BY s1.doc_socio, s1.nome_socio
HAVING COUNT(DISTINCT s1.cnpj) >= 3
 ORDER BY qtd_empresas DESC
 LIMIT 50;

------------------------------------------------------------------
-- 6. Concentração de gasto por município (quem mais contratou)
------------------------------------------------------------------

SELECT municipio,
       COUNT(*)                        AS qtd_contratos,
       SUM(valor_contrato)             AS valor_total,
       COUNT(DISTINCT cnpj_fornecedor) AS fornecedores_distintos
  FROM vw_contratos_homologados
 WHERE municipio IS NOT NULL
 GROUP BY municipio
 ORDER BY valor_total DESC
 LIMIT 30;

------------------------------------------------------------------
-- 7. Contratos COVID-19 com fornecedor sancionado (cruzamento sensível)
------------------------------------------------------------------

SELECT c.cnpj_fornecedor,
       c.razao_social,
       c.orgao,
       c.municipio,
       c.valor_contrato,
       c.data_contrato,
       s.tipo_sancao,
       s.fonte
  FROM vw_contratos_homologados c
  JOIN sancoes s ON c.cnpj_fornecedor = s.cnpj
 WHERE c.flag_covid IS TRUE
 ORDER BY c.valor_contrato DESC NULLS LAST;
