# Dicionário de Dados — `db/dados.duckdb`

> **Para quem vai escrever o score de risco e as red flags.**
> Este documento descreve as 8 tabelas e 7 views do banco, com semântica de cada coluna e os red flags que cada uma destrava. Use junto com `docs/exemplos_queries.sql`.

---

## Princípios não-negociáveis

1. **Linguagem de indício, não de acusação.** Coluna se chama `razao_vs_mediana`, não `eh_sobrepreco`. Score 90/100 = "merece análise humana", nunca "é culpado".
2. **LGPD:** `doc_socio` permanece mascarado (`***NNNNNN**`). Não republicar CPF, endereço residencial, documento de PF.
3. **Rastreabilidade:** todo score precisa listar quais sinais contribuíram. Score sem explicabilidade não tem valor pra Maratona.
4. **Padrão estranho ≠ irregular.** Sempre tem explicação possível (escopo do contrato, urgência, condição especial).

---

## Setup

```bash
duckdb --readonly db/dados.duckdb         # várias abas convivem
```

Em Python:

```python
import duckdb
con = duckdb.connect("db/dados.duckdb", read_only=True)
```

---

## Visão geral

| Tabela | Linhas | CNPJs distintos | Origem | Fase |
|---|---|---|---|---|
| `contratos` | 129.401 | 15.932 | LicitaCon (licitacao + licitante + pessoas) | 1 |
| `empresas` | 4.708.472 | 4.708.472 | Receita — Dados-Empresas-RS.csv | 1 |
| `socios` | 2.519.644 | 1.220.307 | Receita — Socios-RS.csv (`doc_socio` mascarado) | 1 |
| `sancoes` | 16.012 | 10.154 | CEIS + CNEP + CFIL/RS empilhados | 1 |
| `itens` | 527.327 | 6.532 (24% preenchido) | LicitaCon — item.csv | 2 |
| `propostas` | 75.147 | 15.932 | LicitaCon — proposta.csv | 3 |
| `propostas_itens` | 959.348 | 12.445 | LicitaCon — item_prop.csv | 3 |
| `eventos_licitacao` | 177.561 | 1.209 (autor PJ) | LicitaCon — evento_lic.csv | 3 |

| View | Conteúdo |
|---|---|
| `vw_contratos_homologados` | Contratos com fornecedor + valor + data preenchidos |
| `vw_contratos_com_sancao` | Contratos cujo fornecedor está em CEIS/CNEP/CFIL |
| `vw_empresas_sancionadas` | Cadastro RS de empresas sancionadas |
| `vw_sobrepreco_indicios` | Itens com preço unitário ≥ 3× mediana do grupo |
| `vw_proposta_unica` | Licitações com 1 só proposta classificada |
| `vw_cover_bidding_indicios` | Licitações onde 2ª proposta ≥ 2× a vencedora |
| `vw_alteracao_apos_abertura` | Eventos AED/REE após primeira publicação |

---

## Tabela: `contratos`

**Granularidade:** 1 linha por (licitação × fornecedor participante).
**Chave de fornecedor:** `cnpj_fornecedor` (nullable para licitações em andamento).

| Coluna | Tipo | O que significa | Red flag |
|---|---|---|---|
| `cnpj_fornecedor` | VARCHAR | CNPJ de quem participou da licitação | Cruzar com `sancoes`, `socios`, `empresas` |
| `razao_social` | VARCHAR | Nome via `pessoas.csv` | — |
| `orgao` | VARCHAR | Nome do órgão contratante (ex.: "PM DE VACARIA") | — |
| `municipio` | VARCHAR | Derivado por regex em `orgao` (cobre 89,8%) | — |
| `modalidade` | VARCHAR | Código da modalidade — `PRD`=Pregão presencial, `PCE`=Pregão eletrônico, `CPC`=Concorrência, `DSP`=Dispensa, `INX`=Inexigibilidade | `indicio_dispensa_alto_valor` quando DSP/INX > teto legal |
| `objeto` | VARCHAR | Descrição livre do que se compra | NLP futuro: detectar genérico/vago |
| `valor_contrato` | DECIMAL | `VL_HOMOLOGADO` com fallback para `VL_LICITACAO` | Compor com `data_contrato`, `data_abertura` da empresa |
| `data_contrato` | DATE | `DT_HOMOLOGACAO` com fallback para `DT_ABERTURA` | — |
| `numero_contrato` | VARCHAR | `NR_PROCESSO` | — |
| `qtd_participantes` | INTEGER | Calculado por licitação | `alerta_baixa_competicao` se = 1 |
| `flag_covid` | BOOLEAN | Mapeado de `BL_COVID19` | TRUE + sobrepreço = sinal forte |

**Detalhe:** 54.254 linhas têm `cnpj_fornecedor` nulo (licitações sem fornecedor registrado ainda). Use `vw_contratos_homologados` como base default.

---

## Tabela: `empresas`

**Granularidade:** 1 linha por CNPJ no RS.
**100% dos CNPJs únicos e válidos.**

| Coluna | Tipo | O que significa | Red flag |
|---|---|---|---|
| `cnpj` | VARCHAR | Chave | — |
| `razao_social` | VARCHAR | Uppercase normalizado | — |
| `data_abertura` | DATE | Data de constituição | `indicio_empresa_jovem_contrato_grande` (< 180 dias + valor alto) |
| `cnae` | VARCHAR | Código CNAE principal | `indicio_cnae_incompativel_objeto` (NLP/whitelist) |
| `capital_social` | DECIMAL | Capital declarado | `indicio_capital_baixo_contrato_grande` (`valor_contrato / capital_social > 10`) |
| `situacao_cadastral` | VARCHAR | Código (2=ativa, 4=baixada, 8=inapta) | `indicio_empresa_inativa_com_contrato` (≠ 2 + contrato recente) |
| `porte` | VARCHAR | Código de porte | — |
| `endereco` | VARCHAR | Concat de `tipo_logradouro + logradouro + numero + bairro` | NLP futuro: endereços coincidentes entre empresas distintas |
| `municipio` | VARCHAR | Código IBGE (lookup de nome é dívida técnica) | — |

---

## Tabela: `socios`

**Granularidade:** 1 linha por (CNPJ × sócio).
**LGPD:** `doc_socio` mascarado da fonte.

| Coluna | Tipo | O que significa | Red flag |
|---|---|---|---|
| `cnpj` | VARCHAR | CNPJ da empresa | — |
| `nome_socio` | VARCHAR | Nome do sócio (uppercase) | — |
| `doc_socio` | VARCHAR | Sempre mascarado | **Mesmo `doc_socio` em empresas distintas que concorrem na mesma licitação = `indicio_socio_comum_competidores`** |
| `tipo_socio` | VARCHAR | 1=PF, 2=PJ | — |
| `qualificacao` | VARCHAR | Código da função (administrador, sócio, etc.) | — |
| `data_entrada` | DATE | Quando o sócio entrou | Mudança recente + contrato grande = sinal |

**O sinal mais valioso desta tabela:** join consigo mesma por `doc_socio` permite detectar grupos econômicos não declarados. Veja `docs/exemplos_queries.sql` query #5.

---

## Tabela: `sancoes`

**Granularidade:** 1 linha por (CNPJ × sanção).
**Empilhada de 3 fontes** (coluna `fonte` preserva origem).

| Coluna | Tipo | O que significa | Red flag |
|---|---|---|---|
| `cnpj` | VARCHAR | CNPJ sancionado | — |
| `tipo_sancao` | VARCHAR | Categoria (impedimento, inidoneidade, multa) | — |
| `orgao_sancionador` | VARCHAR | Quem aplicou | — |
| `data_inicio` | DATE | Início da vigência | `indicio_sancionado_ativo` se `data_inicio ≤ data_contrato ≤ COALESCE(data_fim, today)` |
| `data_fim` | DATE | Fim (nulo se permanente) | — |
| `fonte` | VARCHAR | `'CEIS'`, `'CNEP'` ou `'CFIL'` | — |

**Distribuição:** CEIS 13.883 (federal — lista negra geral); CNEP 1.632 (federal — Lei Anticorrupção); CFIL 497 (estadual RS).

---

## Tabela: `itens`

**Granularidade:** 1 linha por (licitação × lote × item).
**Chave composta única** (validada em teste).

| Coluna | Tipo | O que significa | Red flag |
|---|---|---|---|
| chave composta licitação + `nr_lote` + `nr_item` | VARCHAR | identifica o item | — |
| `cnpj_fornecedor` | VARCHAR | CNPJ do fornecedor do item (nullable, 24% preenchido) | — |
| `descricao` | VARCHAR | Texto livre original (`DS_ITEM`) | — |
| `descricao_normalizada` | VARCHAR | Chave de agrupamento via `normalizar_descricao_item` (lowercase + sem pontuação + sem dígitos isolados) | Use pra agrupar itens equivalentes entre licitações |
| `quantidade` | DECIMAL | Quantidade contratada | — |
| `unidade` | VARCHAR | `UN`, `KG`, `MES`, etc. | Faz parte da chave de agrupamento de sobrepreço |
| `valor_unitario_estimado` | DECIMAL | Preço previsto pelo órgão | Comparar com `valor_unitario_homologado` para % desvio |
| `valor_unitario_homologado` | DECIMAL | Preço efetivamente contratado | **Insumo do `vw_sobrepreco_indicios`** |
| `valor_total_homologado` | DECIMAL | `quantidade × valor_unitario_homologado` | — |
| `flag_covid` | BOOLEAN | Item COVID-19 | TRUE + sobrepreço = sinal forte |

**Cobertura:** 53% dos itens têm `valor_unitario_homologado` preenchido. Use só esses para análise estatística.

---

## Tabela: `propostas` (Fase 3)

**Granularidade:** 1 linha por (licitação × fornecedor que apresentou proposta).
**Chave composta única.**

| Coluna | Tipo | O que significa | Red flag |
|---|---|---|---|
| chave composta licitação | VARCHAR | identifica a licitação | — |
| `cnpj_proposta` | VARCHAR | CNPJ do proponente | Cruzar com `sancoes`, `empresas`, `socios` |
| `data_proposta` | DATE | Quando a proposta foi enviada | — |
| `resultado_proposta` | VARCHAR | `C`=Classificada, `D`=Desclassificada, `P`=Pendente | Filtro fundamental — só `C` conta pra análise de competição real |
| `valor_total_proposta` | DECIMAL | Valor proposto pelo fornecedor | **Base do `vw_cover_bidding_indicios`** |
| `percentual_desconto` | DECIMAL | Desconto sobre estimativa | — |
| `valor_nota_tecnica` | DECIMAL | Nota técnica (em licitações tipo melhor técnica) | — |
| `data_homologacao` | DATE | Data de homologação do resultado | — |

**Red flags que destrava:**
- **Cover bidding:** vencedora baratíssima + 2ª proposta absurdamente alta (`vw_cover_bidding_indicios`).
- **Proposta única classificada:** após desclassificações, só 1 sobra (`vw_proposta_unica`). Mais forte que `qtd_participantes=1` porque exclui as desclassificadas.
- **Cartel rotativo:** mesmas N empresas aparecem em N licitações alternando vitórias (query #14).
- **Bid clustering:** propostas todas muito próximas (desvio padrão pequeno) sugere combinação.

---

## Tabela: `propostas_itens` (Fase 3)

**Granularidade:** 1 linha por (licitação × lote × item × fornecedor).
**Chave composta única.**

| Coluna | Tipo | O que significa | Red flag |
|---|---|---|---|
| chave composta licitação + `nr_lote` + `nr_item` | VARCHAR | identifica o item | — |
| `cnpj_proposta` | VARCHAR | CNPJ do proponente | — |
| `valor_unitario` | DECIMAL | Preço unitário proposto | Permite refinar sobrepreço: comparar todas as propostas com a mediana, não só a vencedora |
| `valor_total_item` | DECIMAL | Total proposto pro item | — |
| `percentual_desconto`, `percentual_bdi`, `valor_nota_tecnica` | DECIMAL | Detalhes da proposta | — |
| `data_homologacao` | DATE | — | — |
| `resultado_proposta` | VARCHAR | `C`/`D`/`P` | — |
| `resultado_habilitacao` | VARCHAR | `H`=Habilitada, `N`=Não habilitada, `I`=Inabilitada | `indicio_inabilitacao_estranha` quando vencedora tinha proposta + barata mas foi inabilitada |

---

## Tabela: `eventos_licitacao` (Fase 3)

**Granularidade:** 1 linha por evento na linha do tempo.
**Chave composta única** (`licitação + sq_evento`).

| Coluna | Tipo | O que significa | Red flag |
|---|---|---|---|
| chave composta licitação + `sq_evento` | VARCHAR | identifica o evento | — |
| `cd_tipo_fase` | VARCHAR | Fase do processo (`PUB`, `EPU`, etc.) | — |
| `cd_tipo_evento` | VARCHAR | Tipo específico — ver glossário abaixo | **Filtros base de várias red flags** |
| `data_evento` | DATE | Quando o evento ocorreu | Base de todos os sinais temporais |
| `tipo_veiculo_publicacao` | VARCHAR | `J`=Jornal, etc. | — |
| `descricao_publicacao` | VARCHAR | Texto livre | NLP futuro |
| `cnpj_autor` | VARCHAR | Só se autor é PJ (LGPD) | — |
| `data_julgamento` | DATE | Se for julgamento | — |
| `tipo_resultado` | VARCHAR | Resultado do evento | — |
| `nr_lote`, `nr_item` | VARCHAR | Quando o evento se refere a item específico | — |

### Glossário de `cd_tipo_evento` (mais frequentes)

| Código | Significa | Quantidade |
|---|---|---|
| `PUB` | Publicação | 70.926 |
| `ENC` | Encerramento | 56.635 |
| `PUE` | Publicação edital | 42.119 |
| `AED` | **Alteração de edital** | 1.563 ← red flag |
| `REE` | **Republicação edital** | 1.448 ← red flag |
| `ESC` | Esclarecimento | 1.332 |
| `IME` | Impugnação | 832 |
| `SUO` | **Suspensão** | 475 ← red flag |
| `EFI`/`EFC`/`EFH` | Encerramentos diversos | ~900 |
| `REO`/`RHP`/`REI` | Reabertos/reclassificações | ~850 |
| `ANO` | **Anulação** | 210 ← red flag |

**Red flags que destrava:**
- **Alteração de regra após publicação:** `vw_alteracao_apos_abertura` lista eventos AED/REE pós primeira publicação. Particularmente suspeito quando ocorre depois de já haver propostas.
- **Prazo curto entre publicação e abertura:** comparar primeira `PUE` com data de `ENC` ou da primeira proposta — < N dias quebra Lei 14.133.
- **Histórico anormal:** muitas ANO/SUO/REE no mesmo órgão = problemas sistêmicos.

---

## View: `vw_contratos_homologados`

Filtra `contratos` para os com fornecedor + valor + data preenchidos.

**Use como base default** no lugar de `contratos` para qualquer análise estatística.

---

## View: `vw_contratos_com_sancao`

JOIN de `contratos` com `sancoes` por CNPJ. Inclui `tipo_sancao`, `fonte_sancao`, `data_inicio_sancao`, `data_fim_sancao`.

**Não filtra por janela temporal** — peça pra restringir manualmente:
```sql
WHERE data_contrato BETWEEN data_inicio_sancao
                        AND COALESCE(data_fim_sancao, DATE '2100-12-31')
```

---

## View: `vw_empresas_sancionadas`

JOIN de `empresas` com `sancoes`. Cadastro RS de quem está/esteve sancionado.

---

## View: `vw_sobrepreco_indicios` (Fase 2)

Heurística: para cada `(descricao_normalizada, unidade)` com **≥ 10 observações**, calcula mediana do `valor_unitario_homologado`. Itens com **razão ≥ 3×** entram.

| Coluna | Significado |
|---|---|
| `descricao` | Descrição original |
| `unidade` | UN, KG, etc. |
| `mediana` | Preço unitário mediano do grupo |
| `n_obs` | Tamanho da amostra do grupo |
| `valor_unitario_homologado` | Preço efetivamente pago |
| `razao_vs_mediana` | `valor / mediana` — quanto mais alto, mais suspeito |

**Limiares iniciais (n≥10, razão≥3) são chute** — calibrar com revisão humana. 164 indícios atualmente.

**Falsos positivos esperados:** descrições muito genéricas como "MÃO DE OBRA" agrupam itens incomparáveis (escopo de obra vs. hora avulsa).

---

## View: `vw_proposta_unica` (Fase 3)

Licitações com **exatamente 1** proposta classificada após desclassificações.

| Coluna | Significado |
|---|---|
| chave da licitação | — |
| `qtd_propostas_classificadas` | Sempre 1 por construção |

Use como base de `indicio_competicao_zero` no score (mais forte que `qtd_participantes=1` em `contratos`).

---

## View: `vw_cover_bidding_indicios` (Fase 3)

Em licitações com **≥ 3 propostas classificadas**, razão entre a 2ª menor e a menor proposta.

| Coluna | Significado |
|---|---|
| chave da licitação | — |
| `n_classificadas` | Quantidade de propostas classificadas |
| `cnpj_vencedora`, `valor_vencedora` | Menor proposta classificada |
| `cnpj_segunda`, `valor_segunda` | Segunda menor |
| `razao_2a_vs_1a` | `valor_segunda / valor_vencedora` |

**Lógica:** razão muito alta = a 2ª proposta foi "carta marcada" pra dar cara de competição. 168 indícios atualmente.

**Limiar (razão ≥ 2, n ≥ 3) é chute** — calibrar.

---

## View: `vw_alteracao_apos_abertura` (Fase 3)

Eventos `AED` ou `REE` cuja `data_evento > primeira data_publicacao` da licitação.

| Coluna | Significado |
|---|---|
| chave da licitação | — |
| `cd_tipo_evento` | `AED` ou `REE` |
| `data_publicacao` | Primeira `PUE`/`PUB` |
| `data_alteracao` | Data do evento de alteração |
| `dias_apos_publicacao` | Quanto tempo entre publicação e alteração |

**2.892 eventos atualmente.** Alteração tardia (centenas de dias) sugere mudança de regra com licitação já em curso — sinal clássico de favorecimento.

---

## Catálogo de red flags candidatos (resumo pra reunião)

Cada um vira uma coluna `indicio_*` ou `alerta_*` no score, com pontuação a calibrar:

### Por fornecedor (CNPJ)

| Sinal | Como derivar | Força inicial |
|---|---|---|
| `indicio_sancionado_ativo` | EXISTS em `sancoes` ativa na `data_contrato` | +30 |
| `indicio_sancionado_historico` | EXISTS em `sancoes` em qualquer momento | +15 |
| `indicio_empresa_jovem_contrato_grande` | `(data_contrato - data_abertura) < 180 AND valor_contrato > 100k` | +10 |
| `indicio_empresa_inativa_com_contrato` | `situacao_cadastral` ≠ ativa + contrato recente | +20 |
| `indicio_capital_baixo` | `valor_contrato / capital_social > 10` | +10 |
| `indicio_socio_comum_competidores` | mesmo `doc_socio` em fornecedores que concorreram na mesma licitação | +20 |
| `indicio_cartel_recorrente` | par de CNPJs concorre em ≥ 5 licitações juntas | +10 |

### Por licitação

| Sinal | Como derivar | Força inicial |
|---|---|---|
| `alerta_competicao_zero` | EXISTS em `vw_proposta_unica` | +20 |
| `alerta_baixa_competicao` | `qtd_participantes ≤ 2` em `contratos` | +5 |
| `alerta_cover_bidding` | EXISTS em `vw_cover_bidding_indicios` com `razao ≥ 5` | +15 |
| `alerta_dispensa_alto_valor` | `modalidade IN ('DSP','INX')` + `valor_contrato` > teto legal | +25 |
| `alerta_alteracao_regra_tardia` | `vw_alteracao_apos_abertura` com `dias > 30` | +10 |
| `alerta_anulacao_historica` | mesmo órgão com EXISTS em eventos `ANO`/`SUO` | +5 |

### Por item

| Sinal | Como derivar | Força inicial |
|---|---|---|
| `alerta_sobrepreco_alto` | EXISTS em `vw_sobrepreco_indicios` com `razao ≥ 5` | +15 |
| `alerta_sobrepreco_moderado` | EXISTS em `vw_sobrepreco_indicios` com `razao 3-5` | +5 |
| `alerta_covid_sobrepreco` | `flag_covid=TRUE` + sobrepreço | +10 |

---

## Sugestão de estrutura do score

```sql
CREATE OR REPLACE VIEW vw_score_fornecedor AS
WITH sinais AS (
    SELECT
        c.cnpj_fornecedor,
        MAX(CASE WHEN s.cnpj IS NOT NULL AND c.data_contrato BETWEEN s.data_inicio AND COALESCE(s.data_fim, DATE '2100-01-01') THEN 30 ELSE 0 END) AS pts_sancionado_ativo,
        -- ... outros sinais
    FROM contratos c
    LEFT JOIN sancoes s ON s.cnpj = c.cnpj_fornecedor
    GROUP BY c.cnpj_fornecedor
)
SELECT cnpj_fornecedor,
       pts_sancionado_ativo + /* + outros */ AS score,
       ARRAY[
         CASE WHEN pts_sancionado_ativo > 0 THEN 'sancionado_ativo' END,
         -- ...
       ] AS indicios_ativados
  FROM sinais
 WHERE pts_sancionado_ativo > 0; -- ou outro critério
```

Idealmente integrar em `etl/build_db.py` pra recalcular a cada rebuild.

---

## O que NÃO dá pra fazer (limitações)

- **Cruzar CPF entre `sancoes` e `socios`** — sanções de PF foram descartadas no loader (LGPD + schema).
- **`itens.cnpj_fornecedor` cobre só 24%** — pra ligar item ↔ fornecedor, cai via `contratos` por chave da licitação ou via `propostas_itens`.
- **`contratos` perdeu a chave composta** — só tem `orgao` (nome) e `modalidade`. Pra cruzar contrato ↔ proposta/item por licitação, use `cnpj_fornecedor` ou peça pra adicionar a chave composta.
- **`empresas.municipio` é só código IBGE** — sem nome (dívida técnica conhecida).
- **Snapshot estático** — dados de jun/2026, refresh é manual.

---

## Como rodar o pipeline

```bash
uv sync                              # instala deps
uv run python -m etl.build_db        # reconstrói db/dados.duckdb (~2,5 min)
uv run pytest -v                     # 90 testes
duckdb --readonly db/dados.duckdb    # inspeção
```

Pra reler os CSVs e atualizar o inventário (`docs/inventario_fontes.md`):
```bash
uv run python scripts/inventario.py
```

---

## Onde pedir ajuda

- Coluna nova precisa? Adiciono em loader + rebuild.
- Bug em normalização (CNPJ mal limpo, data quebrada)? Manda repro.
- Quer chave composta da licitação em `contratos`? Mudança de 15 min em `load_contratos.py`.
- Quer a Fase 4 (`lote.csv`, `lote_prop.csv`) priorizada? Avisa.

**TL;DR:** Você tem 8 tabelas integradas por CNPJ + chave de licitação. 7 views já são red flags candidatos. Sua tarefa é compor isso num score 0-100 explicável por fornecedor (e/ou por contrato), respeitando linguagem de indício e LGPD.
