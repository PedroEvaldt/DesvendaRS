# Integração do Overview de IA

Este arquivo descreve como operar e manter o overview de IA já integrado ao
dossiê de licitação (`/licitacoes/{chave}`).

## Configuração

Não coloque a chave no código. O módulo lê variáveis de ambiente e também o
arquivo local ignorado `.env`:

```bash
export GEMINI_API_KEY="..."
```

Também aceita `GOOGLE_API_KEY`. O modelo padrão é `gemini-1.5-flash`; pode ser trocado com:

```bash
export GEMINI_MODEL="gemini-1.5-flash"
```

## Uso básico

A rota do front usa `queries.licitacao_ai_context(...)` para montar o contexto e
chama:

```python
from app.ai_overview import generate_licitacao_overview

overview = generate_licitacao_overview(contexto)
```

O retorno tem:

- `enabled`: `False` quando falta API key.
- `status`: `ok`, `missing_key` ou `error`.
- `title`: título curto para o card.
- `summary`: resumo em português.
- `bullets`: pontos de atenção.
- `limitations`: limitações de dados.

## Contexto recomendado

O contexto enviado deve continuar compacto:

- cabeçalho da licitação: órgão, município, modalidade, objeto, valor, data, participantes;
- empresa vencedora: razão social, CNPJ, CNAE, capital social, situação cadastral, data de abertura;
- sanções da vencedora;
- propostas classificadas/desclassificadas, incluindo valores;
- empresas perdedoras;
- principais itens, valores estimados e homologados;
- eventos relevantes do edital;
- red flags automáticas e score, quando disponíveis.

## Cuidados de produto

O texto da IA deve aparecer como apoio, não como conclusão. Mantenha a linguagem de indício:

- correto: "merece revisão humana";
- correto: "não há dados suficientes para avaliar a justificativa";
- evitar: "é fraude", "é irregular", "empresa fraudulenta".

Se `status == "missing_key"`, mostre um estado neutro pedindo a configuração da variável de ambiente. Se `status == "error"`, mostre que a IA está indisponível e mantenha o dossiê normal funcionando.
