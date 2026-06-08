# DesvendaRS — Módulo de Coleta e Armazenamento

Camada de dados do projeto DesvendaRS (MaratonaColab 2026 / SBSC). Lê CSVs públicos
de gastos governamentais já baixados em `data/raw/`, normaliza e gera um único
**DuckDB** (`db/dados.duckdb`) com 8 tabelas integradas por CNPJ + chave de
licitação, 7 views de red flags e tabelas de score explicável — consumido pelo
restante do time (painel, score de risco, busca por IA).

> **Postura do projeto:** levantamos **indícios**, não acusações. Todo nome de
> coluna, flag e mensagem usa linguagem de hipótese. Padrão estranho ≠ culpa.

---

## Pré-requisitos

- [`uv`](https://docs.astral.sh/uv/) instalado (`uv --version` ≥ 0.4)
- Python 3.11+
- CSVs originais em `data/raw/` (não versionados — `.gitignore` cobre)

Arquivos esperados em `data/raw/`:

```
licitacao.csv, pessoas.csv, item.csv, licitante.csv     # LicitaCon/TCE-RS
Dados-Empresas-RS.csv, Socios-RS.csv                    # Receita/CNPJ via BD
20260603_CEIS.csv, 20260603_CNEP.csv                    # Portal da Transparência
SancoesCFIL-RS.csv                                      # PGE-RS
```

---

## Setup

```bash
uv sync                       # instala dependências travadas em uv.lock
```

---

## Baixar/atualizar as fontes automaticamente

```bash
uv run python scripts/baixar_fontes.py --ano 2026
```

O script usa a API CKAN do TCE-RS para localizar os ZIPs de licitações e o Portal da Transparência para CEIS/CNEP. Ele salva e extrai os arquivos em `data/raw/`, pronto para o pipeline do ETL.

Para o CFIL/RS, o fluxo recomendado é:

1. baixar o arquivo manualmente no portal estadual e salvar como `data/raw/SancoesCFIL-RS.csv`; ou
2. informar `--cfil-url` apenas se quiser testar um download direto por URL.

Se `data/raw/SancoesCFIL-RS.csv` já existir, o script usa esse arquivo local automaticamente.

Se quiser apenas listar as URLs que seriam baixadas:

```bash
uv run python scripts/baixar_fontes.py --ano 2026 --listar
```

Se quiser extrair apenas os CSVs de licitações que o ETL usa hoje, passe a lista desejada:

```bash
uv run python scripts/baixar_fontes.py --ano 2026 --filtrar-licitacoes licitacao.csv licitante.csv item.csv pessoas.csv proposta.csv item_prop.csv evento_lic.csv
```

Se você preferir informar a URL manualmente (fallback opcional), use:

```bash
uv run python scripts/baixar_fontes.py --ano 2026 --cfil-url "https://.../SancoesCFIL-RS.csv"
```

Esse parâmetro é opcional. Quando `data/raw/SancoesCFIL-RS.csv` já existe, o script usa o arquivo local e não depende de URL.

## Reconstruir o banco do zero

```bash
uv run python -m etl.build_db
```

O comando:

1. Remove `db/dados.duckdb` se existir.
2. Lê e normaliza cada fonte (loaders em `etl/load_*.py`).
3. Cria as 8 tabelas (`contratos`, `empresas`, `socios`, `sancoes`, `itens`,
   `propostas`, `propostas_itens`, `eventos_licitacao`) e 7 views de red flags
   (`vw_contratos_homologados`, `vw_contratos_com_sancao`, `vw_empresas_sancionadas`,
   `vw_sobrepreco_indicios`, `vw_proposta_unica`, `vw_cover_bidding_indicios`,
   `vw_alteracao_apos_abertura`).
4. Calcula red flags, grava `redflag_eventos`, agrega `scores_fornecedor`,
   `scores_licitacao`, `scores_item` e expõe `vw_possivel_fraude`.
5. Imprime relatório de qualidade (contagens, CNPJs distintos, cardinalidade dos
   JOINs, grupos com massa estatística, indícios de sobrepreço, indícios de cover
   bidding, propostas únicas e entidades com `score_bruto >= 100`).

Tempo típico: **~2,5 min** num SSD com 16 GB de RAM.

---

## Rodar testes

```bash
uv run pytest -v
```

Cobre:

- `tests/test_normalize.py` — funções puras de `etl/normalize.py`
- `tests/test_schema.py` — esquema das tabelas e formato dos CNPJs no banco
- `tests/test_joins.py` — cardinalidade dos cruzamentos por CNPJ
- `tests/test_itens.py` — chave composta única, normalização de descrição,
  view de sobrepreço
- `tests/test_propostas_eventos.py` — Fase 3: chaves compostas, códigos de
  resultado, consistência das views (cover bidding, proposta única, alteração)

Os testes de schema/joins/itens/propostas **dependem** do banco gerado pelo
`build_db`; se ele ainda não foi rodado, são automaticamente skipados.

---

## Rodar o site

```bash
uv run uvicorn web.main:app --reload
```

Abra `http://127.0.0.1:8000`. O site FastAPI lê `db/dados.duckdb` em modo somente
leitura. Se o banco ainda não existir,
mostra um estado vazio com o caminho esperado e o comando de reconstrução.

Para testar a interface sem os CSVs reais, gere um banco pequeno de demonstração:

```bash
uv run python scripts/create_mock_db.py
uv run uvicorn web.main:app --reload
```

O script recusa sobrescrever `db/dados.duckdb` por padrão; use `--force` apenas
para substituir um banco de teste.

---

## Inspeção rápida do banco

```bash
duckdb db/dados.duckdb
```

```sql
SELECT COUNT(*) FROM contratos;
SELECT COUNT(DISTINCT cnpj_fornecedor)
  FROM contratos c JOIN sancoes s ON c.cnpj_fornecedor = s.cnpj;

-- Fornecedores com contrato em RS que estão em alguma lista de sanção:
SELECT * FROM vw_contratos_com_sancao LIMIT 20;

-- Entidades cujo score bruto atingiu o limiar de possível fraude:
SELECT * FROM vw_possivel_fraude ORDER BY score_bruto DESC LIMIT 20;
```

---

## Esquema das tabelas

Definido pela Seção 6 do [`CLAUDE.md`](./CLAUDE.md). Resumo:

| Tabela              | Chave                                                              | Origem                                               | Fase  |
| ------------------- | ------------------------------------------------------------------ | ---------------------------------------------------- | ----- |
| `contratos`         | `cnpj_fornecedor`                                                  | LicitaCon (licitacao + licitante + pessoas)          | 1     |
| `empresas`          | `cnpj`                                                             | Receita — `Dados-Empresas-RS.csv`                    | 1     |
| `socios`            | `cnpj`                                                             | Receita — `Socios-RS.csv` (`doc_socio` mascarado)    | 1     |
| `sancoes`           | `cnpj`                                                             | CEIS + CNEP + CFIL/RS empilhados (coluna `fonte`)    | 1     |
| `itens`             | chave composta licitação + `nr_lote` + `nr_item`                   | LicitaCon — `item.csv`; base de sobrepreço           | 2     |
| `propostas`         | chave composta licitação + `cnpj_proposta`                         | LicitaCon — `proposta.csv`; base de cover bidding    | 3     |
| `propostas_itens`   | chave composta licitação + `nr_lote` + `nr_item` + `cnpj_proposta` | LicitaCon — `item_prop.csv`                          | 3     |
| `eventos_licitacao` | chave composta licitação + `sq_evento`                             | LicitaCon — `evento_lic.csv`; linha do tempo         | 3     |
| `redflag_eventos`   | `escopo` + `entidade_id` + `sinal`                                 | Eventos explicáveis de red flag calculados no DuckDB | Score |
| `scores_fornecedor` | `cnpj`                                                             | Score agregado por fornecedor                        | Score |
| `scores_licitacao`  | chave composta licitação                                           | Score agregado por licitação                         | Score |
| `scores_item`       | chave composta licitação + lote + item                             | Score agregado por item                              | Score |

Detalhes de cada coluna estão em [`docs/dicionario_dados.md`](docs/dicionario_dados.md) —
documento de handoff pro time que fará o score de risco.

Todas as chaves de CNPJ passam por `etl/normalize.limpar_cnpj` (14 dígitos, sem
pontuação). `itens.descricao_normalizada` passa por `normalizar_descricao_item`
para permitir agrupamento por produto entre licitações.

---

## Estrutura do repositório

```
config.py                  paths das fontes e do banco
etl/
  normalize.py             funções puras (CNPJ, data, valor, texto, descrição de item)
  load_contratos.py        ─┐
  load_empresas.py          │ Fase 1
  load_socios.py            │
  load_sancoes.py          ─┘
  load_itens.py             Fase 2 — base de sobrepreço
  load_propostas.py         ─┐
  load_propostas_itens.py    │ Fase 3 — cover bidding, proposta única, timeline
  load_eventos.py            │
  score_redflags.py          calcula red flags e scores explicáveis
  build_db.py              orquestrador → db/dados.duckdb
scripts/
  inventario.py            gera docs/inventario_fontes.md
docs/
  inventario_fontes.md     cabeçalhos reais e % de nulos por CSV
  exemplos_queries.sql     14 queries prontas (sanção, sobrepreço, cover bidding, cartel)
  dicionario_dados.md      handoff: todas as tabelas/views, atributos, red flags
tests/
  test_normalize.py
  test_schema.py
  test_joins.py
  test_itens.py
  test_propostas_eventos.py
```

---

## Restrições (LGPD)

`doc_socio` vem mascarado da fonte (`***NNNNNN**`) e **fica mascarado** —
nada de tentar reconstruir CPF. Nenhuma coluna afirma fraude: usar
`indicio_`, `alerta_`, `sinal_` para futuras flags de risco.
