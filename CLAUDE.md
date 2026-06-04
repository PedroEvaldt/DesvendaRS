# CLAUDE.md — Módulo de Coleta e Armazenamento de Dados

> Este arquivo orienta o assistente de código sobre o contexto, as convenções e as tarefas
> do módulo de **coleta e armazenamento (ETL)** deste projeto. Leia tudo antes de escrever código.

---

## 1. Contexto do projeto

Projeto da **MaratonaColab 2026 (SBSC)** — uma maratona de tecnologia cívica. O objetivo é
**agregar e cruzar dados públicos de gastos governamentais** de várias fontes para fazer
emergir **indícios** de irregularidades em contratações públicas (fraude em licitação,
sobrepreço/superfaturamento, cartel/direcionamento, empresas de fachada e laranjas).

A região-piloto é o **Rio Grande do Sul**.

### Postura obrigatória (não negociável)
O sistema levanta **indícios**, não faz **acusações**. Toda saída deve usar linguagem de
hipótese ("este padrão merece análise"), nunca afirmação de culpa. Um padrão estranho pode
ter explicação legítima. Esse tom deve estar refletido inclusive nos nomes de colunas,
flags e mensagens.

---

## 2. Meu papel neste módulo

Sou responsável pela camada de **dados**: coletar (Extract), limpar e padronizar
(Transform) e carregar (Load) tudo num banco analítico único. O restante do time consome
o banco que eu entregar (painel, score de risco, busca por IA). **A qualidade do que eu
entrego determina a qualidade de tudo que vem depois.**

---

## 3. Stack e decisões de arquitetura

- **Linguagem:** Python 3.11+
- **Gerenciador de pacotes/ambiente:** **uv** (Astral). Usar `uv` para tudo — criar o
  projeto, adicionar dependências e rodar comandos. **Não** usar `pip`/`venv` direto nem
  `requirements.txt`. As dependências ficam no `pyproject.toml` e travadas no `uv.lock`.
- **Banco analítico:** **DuckDB** (local, rápido, sem servidor; lê CSV nativamente)
- **Normalização:** `pandas` (ou `polars` se a memória apertar nos arquivos grandes)
- **Coleta de APIs (se necessário):** `requests` / `httpx`
- **Testes:** `pytest`
- **Chave de junção de TODAS as tabelas:** **CNPJ** — 14 dígitos, sem pontuação, com
  zeros à esquerda. É o que costura contrato ↔ empresa ↔ sócio ↔ sanção. As fontes **não
  têm um identificador comum nativo**; o CNPJ limpo é o que resolve isso.

Os dados já estão **baixados localmente** (não há scraping a fazer no MVP). O trabalho é
ler os CSVs, padronizar e carregar no DuckDB.

---

## 4. Estrutura de diretórios esperada

```
.
├── CLAUDE.md
├── README.md
├── pyproject.toml      # dependências e config do projeto (gerenciado pelo uv)
├── uv.lock             # lockfile do uv — COMMITAR (garante ambiente reproduzível)
├── config.py           # caminhos relativos de data/raw/ e do banco
├── data/
│   ├── raw/            # CSVs originais baixados, flat (NÃO commitar — entra no .gitignore)
│   └── processed/      # CSVs/Parquet limpos (NÃO commitar)
├── etl/
│   ├── __init__.py
│   ├── normalize.py    # funções de limpeza reutilizáveis (CNPJ, datas, valores, texto, descrição de item)
│   ├── load_contratos.py
│   ├── load_empresas.py
│   ├── load_socios.py
│   ├── load_sancoes.py
│   ├── load_itens.py   # Fase 2 — tabela itens (sobrepreço)
│   └── build_db.py     # orquestra tudo: roda os loaders e cria o banco final
├── scripts/
│   └── inventario.py   # gera docs/inventario_fontes.md a partir dos CSVs brutos
├── docs/
│   ├── inventario_fontes.md   # cabeçalho real e % de nulos por CSV
│   └── exemplos_queries.sql   # queries prontas pra revisão humana
├── db/
│   └── dados.duckdb    # banco final — GERADO pelo pipeline (NÃO commitar)
└── tests/
    ├── conftest.py
    ├── test_normalize.py
    ├── test_schema.py
    ├── test_joins.py
    └── test_itens.py   # Fase 2
```

`data/`, `db/` e qualquer arquivo `*.duckdb` ou `*.csv` pesado vão no `.gitignore`.

---

## 5. Fontes de dados (já baixadas em `data/raw/`)

> **Estado inicial do projeto (importante):** o que existe HOJE são **apenas os arquivos
> CSV brutos** dentro de `data/raw/`. **Não existe** banco DuckDB, nem tabela, nem dado
> processado ainda. Todo o módulo consiste em **construir o `db/dados.duckdb` do zero** a
> partir desses CSVs. O `db/dados.duckdb` é uma **saída gerada** pelo pipeline — não
> procure por ele, ele será criado pelo `etl/build_db.py`.

### 5.1. LicitaCon — TCE-RS (âncora do projeto)
Pasta com várias tabelas relacionadas. **Usar no MVP:**

| Arquivo | O que tem | Papel |
|---|---|---|
| `licitacao.csv` | 1 linha por processo: órgão, município, modalidade, objeto, valor, data, tipo | Tabela mãe |
| `pessoas.csv` | Entidades referenciadas (empresas/órgãos/pessoas) com CNPJ/CPF e nome | Mapeia código interno → CNPJ |
| `item.csv` | Itens comprados: descrição, quantidade, unidade, valor unitário, valor total | **Fase 2** — base da análise de sobrepreço |
| `licitante.csv` | Quem participou de cada licitação | Análise de competição |

**Fase 3 (em andamento):** `proposta.csv`, `item_prop.csv`, `evento_lic.csv` já carregados em tabelas dedicadas.
**Fase 4 (não iniciada):** `lote.csv`, `lote_prop.csv` (granularidade intermediária — `propostas_itens` já cobre o caso analítico principal).
**Ignorar:** `documento_lic.csv`, `comissao.csv`, `memcomissao.csv`, `dotacao_lic.csv`, `membrocons.csv`.

> **Chave de ligação entre tabelas do LicitaCon (confirmada na inspeção):** é **composta** —
> `(CD_ORGAO, NR_LICITACAO, ANO_LICITACAO, CD_TIPO_MODALIDADE)`. Não existe um `id_licitacao`
> único na fonte. Ver `docs/inventario_fontes.md` para os cabeçalhos reais.
> Dados são **autodeclarados** pelas entidades, não validados pelo TCE. A qualidade varia
> muito por município (campos vazios, formatos diferentes). Trate isso defensivamente.

### 5.2. Empresas e Sócios — CNPJ da Receita (via Base dos Dados / BigQuery)
- `Dados-Empresas-RS.csv` — cadastro: CNPJ, razão social, data de abertura, CNAE, capital
  social, situação cadastral, porte, endereço (campos separados), município.
- `Socios-RS.csv` — quadro societário (QSA): CNPJ, nome do sócio, documento (mascarado),
  tipo de sócio, qualificação, data de entrada, faixa etária.

### 5.3. Sanções
- `20260603_CEIS.csv` — empresas inidôneas e suspensas (lista negra federal).
- `20260603_CNEP.csv` — empresas punidas pela Lei Anticorrupção.
- `SancoesCFIL-RS.csv` — lista negra estadual do RS.

---

## 6. Esquema alvo (8 tabelas no DuckDB)

Construir exatamente estas 8 tabelas. Tipos de DuckDB indicados. Fase 1 (MVP):
`contratos`, `empresas`, `socios`, `sancoes`. Fase 2: `itens`. Fase 3: `propostas`,
`propostas_itens`, `eventos_licitacao`.

### `contratos` (de LicitaCon: licitacao + item + licitante + pessoas)
| Coluna | Tipo | Origem |
|---|---|---|
| `cnpj_fornecedor` | VARCHAR | pessoas (via licitante) — **chave** |
| `razao_social` | VARCHAR | pessoas |
| `orgao` | VARCHAR | licitacao |
| `municipio` | VARCHAR | licitacao |
| `modalidade` | VARCHAR | licitacao |
| `objeto` | VARCHAR | licitacao / item |
| `valor_contrato` | DECIMAL | licitacao |
| `data_contrato` | DATE | licitacao |
| `numero_contrato` | VARCHAR | licitacao |
| `qtd_participantes` | INTEGER | derivado de licitante |
| `flag_covid` | BOOLEAN | licitacao (se existir o campo) |

### `empresas` (de Dados-Empresas-RS.csv)
| Coluna | Tipo |
|---|---|
| `cnpj` | VARCHAR (**chave**) |
| `razao_social` | VARCHAR |
| `data_abertura` | DATE |
| `cnae` | VARCHAR |
| `capital_social` | DECIMAL |
| `situacao_cadastral` | VARCHAR |
| `porte` | VARCHAR |
| `endereco` | VARCHAR |
| `municipio` | VARCHAR |

### `socios` (de Socios-RS.csv)
| Coluna | Tipo |
|---|---|
| `cnpj` | VARCHAR (**chave**) |
| `nome_socio` | VARCHAR |
| `doc_socio` | VARCHAR (mascarado — manter assim) |
| `tipo_socio` | VARCHAR |
| `qualificacao` | VARCHAR |
| `data_entrada` | DATE |

### `sancoes` (de CEIS + CNEP + CFIL — empilhar numa só tabela)
| Coluna | Tipo |
|---|---|
| `cnpj` | VARCHAR (**chave**) |
| `tipo_sancao` | VARCHAR |
| `orgao_sancionador` | VARCHAR |
| `data_inicio` | DATE |
| `data_fim` | DATE |
| `fonte` | VARCHAR (`'CEIS'`, `'CNEP'` ou `'CFIL'`) |

### `itens` (de `item.csv` — Fase 2, base de sobrepreço)
Granularidade: 1 linha por `(CD_ORGAO, NR_LICITACAO, ANO_LICITACAO, CD_TIPO_MODALIDADE, NR_LOTE, NR_ITEM)`.

| Coluna | Tipo | Origem |
|---|---|---|
| `cd_orgao` | VARCHAR | item — parte da chave da licitação |
| `nr_licitacao` | VARCHAR | item |
| `ano_licitacao` | VARCHAR | item |
| `cd_tipo_modalidade` | VARCHAR | item |
| `nr_lote` | VARCHAR | item |
| `nr_item` | VARCHAR | item |
| `cnpj_fornecedor` | VARCHAR | item `NR_DOCUMENTO` onde `TP_DOCUMENTO='J'` (nullable) |
| `descricao` | VARCHAR | `DS_ITEM` |
| `descricao_normalizada` | VARCHAR | `normalizar_descricao_item(DS_ITEM)` |
| `quantidade` | DECIMAL | `QT_ITENS` |
| `unidade` | VARCHAR | `SG_UNIDADE_MEDIDA` |
| `valor_unitario_estimado` | DECIMAL | `VL_UNITARIO_ESTIMADO` |
| `valor_unitario_homologado` | DECIMAL | `VL_UNITARIO_HOMOLOGADO` |
| `valor_total_homologado` | DECIMAL | `VL_TOTAL_HOMOLOGADO` |
| `flag_covid` | BOOLEAN | `BL_COVID19` |

### `propostas` (de `proposta.csv` — Fase 3)
Granularidade: 1 linha por (licitação × fornecedor que apresentou proposta).

| Coluna | Tipo | Origem |
|---|---|---|
| `cd_orgao`, `nr_licitacao`, `ano_licitacao`, `cd_tipo_modalidade` | VARCHAR | chave da licitação |
| `cnpj_proposta` | VARCHAR | `NR_DOCUMENTO` onde `TP_DOCUMENTO='J'` (**chave de fornecedor**) |
| `data_proposta` | DATE | `DT_PROPOSTA` |
| `resultado_proposta` | VARCHAR | `'C'`=Classificada, `'D'`=Desclassificada, `'P'`=Pendente |
| `valor_total_proposta` | DECIMAL | `VL_TOTAL_PROPOSTA` |
| `percentual_desconto` | DECIMAL | `PC_DESCONTO` |
| `valor_nota_tecnica` | DECIMAL | `VL_NOTA_TECNICA` |
| `data_homologacao` | DATE | `DT_HOMOLOGACAO` |

### `propostas_itens` (de `item_prop.csv` — Fase 3)
Granularidade: 1 linha por (licitação × lote × item × fornecedor). Permite
comparar TODOS os preços propostos no mesmo item — refina sobrepreço.

| Coluna | Tipo | Origem |
|---|---|---|
| chave da licitação + `nr_lote`, `nr_item` | VARCHAR | |
| `cnpj_proposta` | VARCHAR | (**chave de fornecedor**) |
| `valor_unitario` | DECIMAL | `VL_UNITARIO` |
| `valor_total_item` | DECIMAL | `VL_TOTAL_ITEM` |
| `percentual_desconto`, `percentual_bdi`, `valor_nota_tecnica` | DECIMAL | |
| `data_homologacao` | DATE | |
| `resultado_proposta` | VARCHAR | `'C'`/`'D'`/`'P'` |
| `resultado_habilitacao` | VARCHAR | `'H'`=Habilitada, `'N'`=Não habilitada, `'I'`=Inabilitada |

### `eventos_licitacao` (de `evento_lic.csv` — Fase 3)
Granularidade: 1 linha por evento na linha do tempo de uma licitação.

| Coluna | Tipo | Origem |
|---|---|---|
| chave da licitação + `sq_evento` | VARCHAR | |
| `cd_tipo_fase`, `cd_tipo_evento` | VARCHAR | códigos do TCE (`PUB`, `PUE`, `ENC`, `AED`, `REE`, `ANO`, `SUO`...) |
| `data_evento` | DATE | `DT_EVENTO` |
| `tipo_veiculo_publicacao` | VARCHAR | `J`=Jornal, etc. |
| `descricao_publicacao` | VARCHAR | texto livre |
| `cnpj_autor` | VARCHAR | só se autor é PJ (LGPD) |
| `data_julgamento` | DATE | |
| `tipo_resultado` | VARCHAR | |
| `nr_lote`, `nr_item` | VARCHAR | quando o evento se refere a item específico |

### Views geradas pelo `build_db.py`
- `vw_contratos_homologados` — só contratos com fornecedor + valor + data preenchidos.
- `vw_contratos_com_sancao` — contratos cujo fornecedor está em alguma lista de sanção.
- `vw_empresas_sancionadas` — empresas RS sancionadas.
- `vw_sobrepreco_indicios` (Fase 2) — itens com `valor_unitario_homologado` ≥ 3× mediana do grupo `(descricao_normalizada, unidade)` com massa ≥ 10 observações.
- `vw_proposta_unica` (Fase 3) — licitações com 1 só proposta classificada.
- `vw_cover_bidding_indicios` (Fase 3) — em licitações com ≥ 3 propostas classificadas, razão 2ª/1ª ≥ 2× (proposta perdedora artificialmente alta).
- `vw_alteracao_apos_abertura` (Fase 3) — eventos `AED`/`REE` após a primeira publicação.

---

## 7. Regras de normalização (CRÍTICO — fazer em `etl/normalize.py`)

Funções reutilizáveis, cada uma com teste próprio:

1. **`limpar_cnpj(valor)`** — remove tudo que não é dígito, preenche com zeros à esquerda
   até 14 dígitos. Retorna `None` se inválido (não tem como virar 14 dígitos). Esta função
   é a mais importante do módulo — todo JOIN depende dela.
2. **`padronizar_data(valor)`** — converte qualquer formato (`01/05/2025`, `2025-05-01`,
   etc.) para `DATE` ISO. Datas inválidas/futuras absurdas viram `None`, não erro.
3. **`limpar_valor(valor)`** — converte texto monetário (`"R$ 1.234,56"`, `"1234.56"`) para
   número. Trata vírgula decimal e separador de milhar do padrão brasileiro.
4. **`normalizar_texto(valor)`** — trim, colapsa espaços múltiplos, padroniza maiúsculas
   para razões sociais (ajuda a casar nomes com variação).
5. **`normalizar_descricao_item(texto)`** (Fase 2) — lowercase, colapsa espaços, remove
   pontuação e dígitos isolados. É a chave de agrupamento da view de sobrepreço; mesmo
   produto descrito de N maneiras precisa cair no mesmo bucket.

> Aplicar `limpar_cnpj` em **todas** as colunas de CNPJ de **todas** as fontes antes de
> qualquer JOIN. Esse é o ponto onde o cruzamento entre bases dá certo ou falha.

---

## 8. O que preciso que você faça (ordem sugerida)

**Fase 1 (MVP) — ✅ concluída** (commits `c76e589..ff1b14c`):
bootstrap com `uv`, inventário, `normalize.py`, 4 loaders, `build_db.py`,
testes, README, queries de exemplo. 52 testes verdes.

**Fase 2 (concluída) — mergeada em `main`:** tabela `itens` + view
`vw_sobrepreco_indicios` + `normalizar_descricao_item`.

**Fase 3 (em andamento) — branch `feature/propostas-eventos-lotes`:**

1. **3 loaders novos**: `load_propostas.py`, `load_propostas_itens.py`,
   `load_eventos.py`.
2. **3 tabelas novas**: `propostas`, `propostas_itens`, `eventos_licitacao`.
3. **3 views novas**: `vw_proposta_unica`, `vw_cover_bidding_indicios`,
   `vw_alteracao_apos_abertura`.
4. **Testes**: `test_propostas_eventos.py` cobre chaves compostas, códigos
   conhecidos e consistência das views.
5. **`docs/exemplos_queries.sql`**: queries de cover bidding, proposta única,
   alteração de edital.
6. **`docs/dicionario_dados.md`**: documento de handoff pra quem fará o
   score de risco — todas as 8 tabelas com semântica e red flags por coluna.

**Fase 4 (não iniciada):** carregar `lote.csv` e `lote_prop.csv` para
análise por lote (granularidade intermediária). Score de risco consolidando
indícios `indicio_*` em score 0-100 fica com outro membro do time.

Trabalhe em **incrementos pequenos e testáveis**. Rode o código a cada etapa; não escreva
o pipeline todo de uma vez. Se um arquivo for grande demais pra carregar na memória, leia
em chunks ou use `polars` / leitura direta do DuckDB sobre o CSV.

---

## 9. Testes obrigatórios (`pytest`)

- **`test_normalize.py`**: casos de `limpar_cnpj` (com pontuação, com menos de 14 dígitos,
  com lixo, vazio), `padronizar_data` (formatos BR e ISO, data inválida), `limpar_valor`
  (padrão brasileiro com R$ e vírgula).
- **`test_schema.py`**: depois do build, cada tabela tem exatamente as colunas e tipos da
  seção 6; coluna `cnpj`/`cnpj_fornecedor` nunca tem valor com pontuação ou ≠ 14 dígitos
  (exceto nulos esperados).
- **`test_joins.py`**: existe uma fração razoável (>0) de CNPJs de `contratos` que casam
  com `empresas` e com `sancoes`. Se **nenhum** casar, o pipeline está quebrado (provável
  erro de normalização de CNPJ) — o teste deve falhar e gritar isso.

Inclua também **checagens de qualidade** no `build_db.py` (não como teste, mas como log):
contagem de nulos por coluna-chave, nº de datas inválidas descartadas, nº de CNPJs que não
puderam ser normalizados.

---

## 10. Convenções de código

- Nomes de variáveis, colunas e arquivos em **português**, `snake_case`.
- Funções pequenas e puras na `normalize.py`; loaders não duplicam lógica de limpeza.
- Sem caminhos absolutos hardcoded — use caminhos relativos a partir da raiz do projeto
  (idealmente um `config.py` ou constantes com os paths de `data/raw/`).
- Docstrings curtas em português explicando o "porquê", não o "o quê".
- Commits pequenos e descritivos.

---

## 11. Restrições importantes (LGPD e responsabilidade)

- **Não republicar CPF completo, endereço residencial ou documento de pessoa física.** O
  `doc_socio` vem mascarado da fonte — **mantenha mascarado**, nunca tente "completar".
- Dados de sócios só onde a transparência pública autoriza; tratar como sensível.
- Sempre preservar a rastreabilidade: cada tabela deve permitir saber de qual fonte e de
  qual arquivo o dado veio (a coluna `fonte` em `sancoes` é exemplo disso).
- Nenhuma flag ou nome de coluna deve afirmar fraude — usar termos como `indicio_`,
  `alerta_`, `sinal_`.

---

## 12. Comandos

```bash
# configurar o projeto na primeira vez
uv init                                      # se ainda não houver pyproject.toml
uv add duckdb pandas polars requests httpx   # dependências do projeto
uv add --dev pytest                          # dependência de desenvolvimento

# se o pyproject.toml/uv.lock já existem, só sincronizar o ambiente
uv sync

# rodar o pipeline completo (lê data/raw/ e GERA db/dados.duckdb do zero)
uv run python -m etl.build_db

# rodar os testes
uv run pytest -v

# abrir o banco pra inspeção rápida (depois de gerado)
duckdb db/dados.duckdb
```

---

## 13. Definição de pronto (este módulo)

### Fase 1 (MVP) — ✅ concluída
- [x] As 4 tabelas existem em `db/dados.duckdb` com o esquema da seção 6.
- [x] CNPJs normalizados (14 dígitos, sem pontuação) em todas as tabelas.
- [x] CNPJs casam entre `contratos`, `empresas`, `socios` e `sancoes` (comprovado por teste).
- [x] Todos os testes do `pytest` passam.
- [x] `README.md` explica como reconstruir o banco do zero.
- [x] `docs/inventario_fontes.md` documenta as colunas reais de cada fonte.

### Fase 2 (sobrepreço) — ✅ concluída
- [x] Tabela `itens` existe com 1 linha por (licitação × lote × item).
- [x] `descricao_normalizada` agrupa o suficiente (1.246 grupos com massa ≥ 10).
- [x] `vw_sobrepreco_indicios` devolve resultados não-triviais (164 indícios).
- [x] Testes 100% verdes.

### Fase 3 (propostas + eventos) — em andamento
- [ ] Tabelas `propostas`, `propostas_itens`, `eventos_licitacao` com chaves compostas únicas.
- [ ] Views `vw_proposta_unica`, `vw_cover_bidding_indicios`, `vw_alteracao_apos_abertura` devolvem resultados não-triviais.
- [ ] `docs/dicionario_dados.md` cobre as 8 tabelas + 7 views com semântica e red flags.
- [ ] Testes 100% verdes (existentes + novos).
