# CLAUDE.md — Módulo do Site (FastAPI)

> Este arquivo orienta o assistente de código sobre o contexto, as convenções e as tarefas
> do módulo de **site/interface web (FastAPI)** deste projeto. Leia tudo antes de escrever código.

---

## 1. Contexto do projeto

Projeto da **MaratonaColab 2026 (SBSC)** — uma maratona de tecnologia cívica. O objetivo é
**agregar e cruzar dados públicos de gastos governamentais** de várias fontes para fazer
emergir **indícios** de irregularidades em contratações públicas (fraude em licitação,
sobrepreço/superfaturamento, cartel/direcionamento, empresas de fachada e laranjas).

A região-piloto é o **Rio Grande do Sul**.

### Postura obrigatória (não negociável)
O sistema levanta **indícios**, não faz **acusações**. Toda saída na interface deve usar
linguagem de hipótese ("este padrão merece análise"), nunca afirmação de culpa. Um padrão
estranho pode ter explicação legítima. Esse tom deve estar refletido em **títulos, rótulos,
mensagens, tooltips e textos de tela** — não só no backend. Score 90/100 = "merece análise
humana", nunca "é culpado".

---

## 2. Meu papel neste módulo

Sou responsável pela camada de **aplicação web**: construir o **site (FastAPI)** que deixa
um usuário (jornalista, auditor, cidadão) **navegar pelas empresas de maior risco, pesquisar
licitações por cidade e visualizar os indícios** já calculados pela trilha de dados. **Eu não
produzo dados nem o score** — eu **leio** o banco analítico `db/dados.duckdb` (read-only) e o
apresento da forma mais clara e investigável possível.

A divisão de trabalho do time:
- **Trilha de dados (ETL):** constrói as 8 tabelas + 7 views no DuckDB. **Já está pronta.**
- **Trilha de score (já roda no `build_db`):** `etl/score_redflags.py` grava
  `redflag_eventos` (eventos atômicos com evidência) e agrega em `scores_fornecedor`,
  `scores_licitacao`, `scores_item`, `scores_orgao` + `vw_possivel_fraude`.
- **Eu (site):** transformo isso em ranking de empresas + busca de licitações + dossiês
  explicáveis. O site **degrada com elegância** se as tabelas de score não existirem.

---

## 3. Stack e decisões de arquitetura

- **Linguagem:** Python 3.11+
- **Gerenciador de pacotes/ambiente:** **uv** (Astral). Usar `uv` para tudo — adicionar
  dependências e rodar comandos. **Não** usar `pip`/`venv` direto nem `requirements.txt`.
- **Web:** **FastAPI** + **Jinja2** (HTML renderizado no servidor) + **Tailwind via CDN** +
  HTMX leve. Server-side rendering primeiro; visual evolui sem trocar de stack (e o FastAPI já
  serve de base para uma API JSON/SPA no futuro).
- **Acesso a dados:** **DuckDB em modo read-only** — o site **nunca escreve** no banco.
  Toda query passa por `app/db.py` (`connect(..., read_only=True)`, `query_df`).
- **Manipulação:** `pandas` (DataFrames vindos do DuckDB via `fetchdf()`).
- **Testes:** `pytest` — `tests/test_web.py` (rotas, via `TestClient`) e
  `tests/test_app_queries.py` (queries), ambos contra o **mock**.

**Chave de junção de tudo:** **CNPJ** (14 dígitos, sem pontuação, zeros à esquerda) — é o que
costura contrato ↔ empresa ↔ sócio ↔ sanção ↔ proposta. As queries cruzam por CNPJ; não
reimplementar limpeza de CNPJ aqui (já vem normalizado do banco).

> **O site é resiliente à ausência de relações.** `app/db.py::inspect_database` descobre quais
> tabelas/views existem; as queries usam `relation_exists(...)` (e `has_score_tables`) antes de
> tocar numa relação opcional. Se o banco não existe ou faltam tabelas, o site renderiza
> `indisponivel.html` em vez de quebrar. **Mantenha esse padrão** — nunca assuma que uma view
> ou tabela de score existe.

---

## 4. Estrutura de diretórios do site

```
.
├── CLAUDE.md
├── config.py               # caminhos (DB_PATH = db/dados.duckdb) — NÃO hardcodar paths
├── app/                    # camada de dados/queries (sem dependência de framework web)
│   ├── __init__.py
│   ├── db.py               # camada DuckDB read-only + inspeção de schema (DatabaseStatus)
│   ├── queries.py          # TODA a lógica SQL (ranking, busca, dossiês) — devolve pd.DataFrame
│   └── dossier.py          # exporta dossiê Markdown (reutilizável pelo site)
├── web/                    # site FastAPI
│   ├── __init__.py
│   ├── main.py             # rotas, Jinja2Templates, filtros (moeda/numero/nivel), get_conn
│   ├── templates/          # base.html, index.html, empresa.html, licitacoes.html,
│   │                       #   licitacao.html, indisponivel.html
│   └── static/style.css    # ajustes próprios (badges de score) — Tailwind vem do CDN
├── db/
│   └── dados.duckdb        # banco analítico — ENTRADA do site (gerado pelo ETL; NÃO commitar)
├── docs/                   # documentação da trilha de dados — REFERÊNCIA (ler, não editar)
│   ├── dicionario_dados.md # ⭐ semântica das 8 tabelas + 7 views + red flags por coluna
│   ├── redflags.md · catalogo_redflags_score.md
│   ├── exemplos_queries.sql · inventario_fontes.md
└── tests/
    ├── test_web.py         # rotas do site (TestClient) contra o mock
    └── test_app_queries.py # queries (ranking, dossiês, licitações) contra o mock
```

**Separação de responsabilidades:**
- `web/main.py` só orquestra rotas + monta o contexto dos templates. **Sem SQL solto aqui.**
- `app/queries.py` concentra todo SQL. Cada consulta recebe a conexão e devolve `pd.DataFrame`
  (ou dict de DataFrames). É o lugar testável e **reaproveitado por testes e site**.
- `web/templates/` cuida da apresentação; formatação BR via filtros Jinja em `web/main.py`.
- Nunca duplicar SQL fora de `app/queries.py`.

**Banco nos testes/deploy:** `web/main.py` lê o caminho de `DESVENDARS_DB` (ou `config.DB_PATH`).
Os testes constroem um mock em `tmp` e apontam essa env var para ele.

`data/`, `db/` e qualquer `*.duckdb`/`*.csv` pesado ficam no `.gitignore`.

---

## 5. O banco que eu consumo (referência de schema)

> **Eu não construo isto** — é entrada do app. A referência canônica e completa (semântica de
> cada coluna + red flag que destrava) está em **`docs/dicionario_dados.md`**. Resumo abaixo.

### 8 tabelas (integradas por CNPJ + chave de licitação)

| Tabela | Granularidade | Colunas-chave para o app |
|---|---|---|
| `contratos` | licitação × fornecedor | `cnpj_fornecedor`, `razao_social`, `orgao`, `municipio`, `modalidade`, `objeto`, `valor_contrato`, `data_contrato`, `qtd_participantes`, `flag_covid` |
| `empresas` | 1 por CNPJ | `cnpj`, `razao_social`, `data_abertura`, `cnae`, `capital_social`, `situacao_cadastral` (2=ativa), `porte` |
| `socios` | CNPJ × sócio | `cnpj`, `nome_socio`, `doc_socio` (**mascarado**), `qualificacao`, `data_entrada` |
| `sancoes` | CNPJ × sanção | `cnpj`, `tipo_sancao`, `orgao_sancionador`, `data_inicio`, `data_fim`, `fonte` (CEIS/CNEP/CFIL) |
| `itens` | licitação × lote × item | `descricao`, `unidade`, `valor_unitario_homologado`, `cnpj_fornecedor` (24% preenchido) |
| `propostas` | licitação × fornecedor | `cnpj_proposta`, `resultado_proposta` (C/D/P), `valor_total_proposta` |
| `propostas_itens` | licitação × lote × item × fornecedor | `cnpj_proposta`, `valor_unitario`, `resultado_habilitacao` |
| `eventos_licitacao` | 1 por evento | `cd_tipo_evento` (AED/REE/SUO/ANO = red flags), `data_evento` |

### 7 views (red flags já calculadas — USE-AS, não recalcule)

| View | Conteúdo | Onde já aparece no app |
|---|---|---|
| `vw_contratos_homologados` | contratos com fornecedor+valor+data | **base default da busca** (`_contracts_base`) |
| `vw_contratos_com_sancao` | fornecedor sancionado | métrica "fornecedores com sanção" |
| `vw_empresas_sancionadas` | cadastro RS de sancionados | — |
| `vw_sobrepreco_indicios` | item ≥ 3× mediana do grupo | aba "Itens e preço" + score provisório |
| `vw_proposta_unica` | 1 só proposta classificada | painel de sinais por licitação |
| `vw_cover_bidding_indicios` | 2ª proposta ≥ 2× a 1ª | painel de sinais por licitação |
| `vw_alteracao_apos_abertura` | AED/REE após publicação | painel de sinais por licitação |

### Limitações conhecidas que afetam o site
- **`contratos` agora preserva a chave composta** `(cd_orgao, nr_licitacao, ano_licitacao,
  cd_tipo_modalidade)` + `cnpj_vencedor` — foi o que destravou cidade ↔ licitação ↔ propostas.
- **`cnpj_vencedor` só existe onde a fonte registrou vencedor PJ homologado** (~5k de 132k);
  no dossiê da licitação, o bloco "empresa vencedora" pode ficar vazio (fallback já tratado).
- **`itens.cnpj_fornecedor` cobre só 24%** — ligação item↔fornecedor é parcial.
- **`empresas.municipio` é só código IBGE** (sem nome — dívida técnica da fonte).
- **Snapshot estático** (dados jun/2026, refresh manual).

---

## 6. O que o site faz hoje

Rotas em `web/main.py`, templates em `web/templates/`, SQL em `app/queries.py`:

| Rota | Função | Queries (em `app/queries.py`) |
|---|---|---|
| `GET /` | **Home:** ranking de empresas com mais red flags + score, busca por nome/CNPJ, métricas gerais | `top_empresas_risco`, `overview` |
| `GET /empresas/{cnpj}` | **Dossiê da empresa:** score, sinais **com evidência** (descrição via `RED_FLAGS`), cadastro, sanções, contratos, sócios (mascarado) | `empresa_dossie` |
| `GET /licitacoes?municipio=` | **Busca por cidade:** select de município → lista de licitações | `municipios`, `licitacoes_por_municipio` |
| `GET /licitacoes/{cd_orgao}/{nr}/{ano}/{mod}` | **Dossiê da licitação:** cabeçalho, red flags, vencedora, **todos os participantes**, **propostas perdedoras** | `licitacao_detalhe`, `propostas_concorrentes`, `contratos_da_licitacao` |
| `GET /healthz` | liveness | — |

**Padrões a manter:**
- Home/dossiês saem das tabelas de score (`scores_fornecedor`, `redflag_eventos`); proteger com
  `has_score_tables(status)` e degradar para `indisponivel.html` quando faltarem.
- O elo cidade ↔ licitação ↔ propostas usa a **chave composta** já presente em `contratos`.
- Antes de criar query nova, checar se já existe em `app/queries.py` ou se uma view/tabela de
  score resolve. **Todo SQL novo vai em `app/queries.py`**, devolvendo `pd.DataFrame`.

---

## 7. Convenções de código

- Nomes de variáveis, colunas e arquivos em **português**, `snake_case` (o SQL e as colunas do
  banco já são em PT). Docstrings curtas em PT explicando o "porquê".
- **SQL só em `app/queries.py`**; rotas/contexto em `web/main.py`; apresentação em
  `web/templates/`.
- **Sem caminhos absolutos** — usar `config.DB_PATH` (ou `DESVENDARS_DB`).
- **Moeda no padrão brasileiro** sempre via o filtro Jinja `moeda` (R$ 1.234,56).
- Toda query de relação opcional protegida por `relation_exists(status, ...)` / `has_score_tables`.
- Commits pequenos e descritivos.

---

## 8. Restrições importantes (LGPD e responsabilidade)

- **Nunca exibir CPF completo, endereço residencial ou documento de PF.** `doc_socio` vem
  mascarado do banco — **manter mascarado na tela**, nunca tentar "completar" ou reverter.
- Dados de sócios só na medida em que a transparência pública autoriza; tratar como sensível.
- **Rastreabilidade:** todo indício exibido deve deixar claro de onde veio (qual fonte/coluna).
  O dossiê e as abas devem permitir ao usuário auditar o sinal.
- **Nenhum rótulo/mensagem afirma fraude.** Usar `indício`, `alerta`, `sinal`, "merece análise".

---

## 9. Comandos

```bash
# sincronizar o ambiente (pyproject.toml + uv.lock já existem)
uv sync

# rodar o site
uv run uvicorn web.main:app --reload         # http://127.0.0.1:8000

# rodar os testes
uv run pytest tests/test_web.py tests/test_app_queries.py -v   # site + queries (contra o mock)
uv run pytest -v                                               # suíte completa

# mock rápido para desenvolver/testar o site sem o rebuild pesado
uv run python scripts/create_mock_db.py --force

# inspecionar o banco que o site lê (read-only)
duckdb --readonly db/dados.duckdb
```

> Se `db/dados.duckdb` não existir, é gerado pela trilha de ETL com
> `uv run python -m etl.build_db` (recria também as tabelas de score). O site **não** gera o
> banco; só o consome. Use `DESVENDARS_DB=/caminho.duckdb` para apontar outro banco.

---

## 10. Definição de pronto (módulo do site)

- [x] **Home** lista empresas por quantidade de red flags + score; clique abre o dossiê.
- [x] **Dossiê da empresa** mostra os sinais **com evidência**, cadastro, sanções e contratos.
- [x] **Busca de licitações por cidade** + dossiê da licitação (vencedora, participantes,
      propostas perdedoras).
- [x] Indícios exibidos com **linguagem de hipótese** e rastreáveis à fonte.
- [x] `doc_socio` permanece mascarado; nenhum dado de PF sensível é exibido.
- [x] Site **não quebra** se uma tabela/score faltar (`indisponivel.html`).
- [x] Testes de `tests/test_web.py` e `tests/test_app_queries.py` passam.
- [x] Moeda e datas no padrão brasileiro.
- [ ] **Próximo:** capricho visual (design além do Tailwind básico).
