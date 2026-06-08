# Integração do Overview de IA

Este arquivo descreve como plugar o módulo novo `app/ai_overview.py` no front quando a branch visual estiver pronta.

## Configuração

Não coloque a chave no código. O módulo lê:

```bash
export GEMINI_API_KEY="..."
```

Também aceita `GOOGLE_API_KEY`. O modelo padrão é `gemini-1.5-flash`; pode ser trocado com:

```bash
export GEMINI_MODEL="gemini-1.5-flash"
```

## Uso básico

Monte um dicionário com os dados da licitação e chame:

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

Enviar apenas dados úteis e compactos:

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
