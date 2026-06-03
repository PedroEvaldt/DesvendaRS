# DesvendaRS — Módulo de Coleta e Armazenamento

Camada de dados do projeto DesvendaRS (MaratonaColab 2026 / SBSC). Lê CSVs públicos
de gastos governamentais já baixados em `data/raw/`, normaliza e gera um único
**DuckDB** (`db/dados.duckdb`) com 5 tabelas integradas por CNPJ + chave de
licitação e 4 views de cruzamento — consumido pelo restante do time (painel,
score de risco, busca por IA).

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

## Reconstruir o banco do zero

```bash
uv run python -m etl.build_db
```

O comando:
1. Remove `db/dados.duckdb` se existir.
2. Lê e normaliza cada fonte (loaders em `etl/load_*.py`).
3. Cria as 5 tabelas (`contratos`, `empresas`, `socios`, `sancoes`, `itens`) e
   4 views de cruzamento (`vw_contratos_homologados`, `vw_contratos_com_sancao`,
   `vw_empresas_sancionadas`, `vw_sobrepreco_indicios`).
4. Imprime relatório de qualidade (contagens, CNPJs distintos, cardinalidade dos
   JOINs entre tabelas, grupos com massa estatística e indícios de sobrepreço).

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

Os testes de schema/joins/itens **dependem** do banco gerado pelo `build_db`; se
ele ainda não foi rodado, são automaticamente skipados.

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
```

---

## Esquema das tabelas

Definido pela Seção 6 do [`CLAUDE.md`](./CLAUDE.md). Resumo:

| Tabela     | Chave                                                       | Origem                          |
|------------|-------------------------------------------------------------|---------------------------------|
| `contratos`| `cnpj_fornecedor`                                           | LicitaCon (licitacao + licitante + pessoas) |
| `empresas` | `cnpj`                                                      | Receita — `Dados-Empresas-RS.csv` |
| `socios`   | `cnpj`                                                      | Receita — `Socios-RS.csv` (`doc_socio` permanece mascarado) |
| `sancoes`  | `cnpj`                                                      | CEIS + CNEP + CFIL/RS empilhados (coluna `fonte` indica origem) |
| `itens`    | `(cd_orgao, nr_licitacao, ano_licitacao, cd_tipo_modalidade, nr_lote, nr_item)` | LicitaCon — `item.csv`; base da análise de sobrepreço |

Todas as chaves de CNPJ passam por `etl/normalize.limpar_cnpj` — 14 dígitos, sem
pontuação, com zeros à esquerda preservados. `itens.descricao_normalizada` passa
por `etl/normalize.normalizar_descricao_item` para permitir agrupamento por
produto entre licitações diferentes.

---

## Estrutura do repositório

```
config.py                  paths das fontes e do banco
etl/
  normalize.py             funções puras (CNPJ, data, valor, texto, descrição de item)
  load_contratos.py
  load_empresas.py
  load_socios.py
  load_sancoes.py
  load_itens.py            Fase 2 — base de sobrepreço
  build_db.py              orquestrador → db/dados.duckdb
scripts/
  inventario.py            gera docs/inventario_fontes.md
docs/
  inventario_fontes.md     cabeçalhos reais e % de nulos por CSV
  exemplos_queries.sql     10 queries prontas (sobrepreço, sanção, COVID, etc.)
tests/
  test_normalize.py
  test_schema.py
  test_joins.py
  test_itens.py
```

---

## Restrições (LGPD)

`doc_socio` vem mascarado da fonte (`***NNNNNN**`) e **fica mascarado** —
nada de tentar reconstruir CPF. Nenhuma coluna afirma fraude: usar
`indicio_`, `alerta_`, `sinal_` para futuras flags de risco.
