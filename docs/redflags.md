# Catálogo de Red Flags

> Documento de referência rápida para sinais de risco no banco analítico.
> Não afirma irregularidade; cada item é um indício que merece revisão humana.

## Objetivo

Concentrar os principais sinais de alerta que podem ser extraídos das tabelas e views do projeto.
Use este catálogo como base para priorizar implementações de score e para conectar dados com auditoria.

## Principais fontes

- `contratos` — participante, valor, data, órgão, modalidade, objeto.
- `empresas` — cadastro da Receita, capital social, situação cadastral, CNAE.
- `socios` — sócios mascarados, datas de entrada, qualificação.
- `sancoes` — CEIS, CNEP, CFIL/RS.
- `itens` — preços estimados e homologados por item.
- `propostas` e `propostas_itens` — competição, valores e resultados.
- `eventos_licitacao` — alterações de edital, suspensões, anulações e prazos.
- Views existentes: `vw_contratos_homologados`, `vw_contratos_com_sancao`, `vw_empresas_sancionadas`, `vw_sobrepreco_indicios`, `vw_proposta_unica`, `vw_cover_bidding_indicios`, `vw_alteracao_apos_abertura`.

## Red Flags por escopo

### 1. Fornecedor

- `indicio_sancionado_ativo`: fornecedor tem sanção vigente na data do contrato.
- `indicio_sancionado_historico`: fornecedor aparece em lista de sanções em qualquer período.
- `indicio_empresa_inativa_com_contrato`: CNPJ com situação cadastral não ativa participa de contrato recente.
- `indicio_empresa_jovem_contrato_grande`: empresa aberta há menos de 180 dias recebe contrato elevado.
- `indicio_capital_baixo`: contrato muito maior que o capital social declarado.
- `indicio_socio_comum_competidores`: empresas concorrentes compartilham sócio mascarado.
- `indicio_socio_recente_antes_contrato`: sócio entra pouco antes de contrato relevante.
- `indicio_endereco_compartilhado_competidores`: concorrentes têm o mesmo endereço/CEP/logradouro.
- `indicio_cartel_recorrente`: par de CNPJs concorre junto frequentemente.
- `indicio_rotacao_vencedores`: fornecedores alternam vitórias em licitações similares.
- `indicio_fornecedor_concentrado_por_orgao`: fornecedor concentra gastos em um único órgão.

### 2. Licitação

- `alerta_competicao_zero`: só uma proposta classificada após desclassificações.
- `alerta_baixa_competicao`: até dois participantes na licitação.
- `alerta_cover_bidding`: segunda melhor proposta muito maior que a primeira.
- `alerta_dispensa_alto_valor`: dispensa/inexigibilidade acima do teto legal.
- `indicio_fracionamento_dispensa`: dispensas similares e repetidas abaixo do teto que somadas ultrapassam o limite.
- `indicio_vencedor_recorrente_mesmo_objeto`: mesmo fornecedor vence repetidamente objetos parecidos no mesmo órgão.
- `indicio_propostas_muito_proximas`: propostas classificadas com dispersão anormalmente baixa.
- `indicio_desconto_inexistente_em_ambiente_competitivo`: vencedor não diminui valor estimado apesar de competição.
- `alerta_alteracao_regra_tardia`: AED/REE após a abertura do processo.
- `indicio_alteracao_edital_beneficia_vencedor`: alteração/republicação que parece favorecer o vencedor final.
- `alerta_anulacao_historica`: órgão com muitas anulações ou suspensões.
- `indicio_prazo_curto_publicacao_abertura`: prazo entre edital e abertura insuficiente para modalidade.
- `alerta_orcamento_sigiloso_baixa_competicao`: orçamento sigiloso combinado com baixa competição.

### 3. Item e preço

- `alerta_sobrepreco_alto`: preço homologado ≥ 5× mediana do grupo de itens comparáveis.
- `alerta_sobrepreco_moderado`: preço homologado entre 3× e 5× a mediana.
- `alerta_covid_sobrepreco`: item COVID com indicativo de sobrepreço.
- `indicio_preco_estimado_acima_mediana`: estimativa do órgão já está muito acima da mediana histórica.
- `indicio_proposta_item_perdedora_artificialmente_alta`: proposta derrotada muito mais cara que a menor no mesmo item.
- `indicio_desclassificacao_conveniente`: proposta mais barata desclassificada e vence proposta mais cara.
- `indicio_fonte_referencia_ausente_preco_alto`: preço alto sem fonte de referência informada.

### 4. Órgão e padrão sistêmico

- `indicio_orgao_sobrepreco_recorrente`: órgão com muitos itens fora da mediana.
- `indicio_orgao_baixa_competicao_recorrente`: órgão com alta taxa de licitações de baixa competição.
- `indicio_orgao_dispensas_recorrentes`: órgão usa dispensa/inexigibilidade acima do padrão.
- `indicio_fornecedor_exclusivo_orgao`: fornecedor quase exclusivo de um único órgão.

### 5. Sinais textuais / LLM

- `llm_justificativa_inexigibilidade_fraca`: justificativa textual de dispensa/inexigibilidade fraca ou genérica.
- `llm_objeto_vago_ou_direcionado`: objeto da licitação parece genérico demais ou direcionado.
- `llm_cnae_incompativel_objeto`: CNAE da empresa não bate com o objeto ou itens.
- `llm_fracionamento_semantico_objetos`: dispensas semanticamente próximas entre processos distintos.
- `llm_alteracao_edital_direcionadora`: alteração de edital parece restringir competição.
- `llm_impugnacao_indica_restricao`: impugnações ou esclarecimentos sugerem exigências restritivas.
- `llm_item_generico_incomparavel`: item genérico demais para análise de sobrepreço.
- `llm_preco_plausivel_pelo_contexto`: avaliar se preço alto tem explicação legítima.
- `llm_texto_copiado_entre_editais`: textos muito semelhantes entre editais diferentes.

## Recomendações de uso

- Priorize sinais com boa cobertura de dados e baixa nulidade.
- Evite acumular flags semelhantes sem ajuste de peso.
- Sempre trate como indícios: o output deve dizer "merece análise humana".
- Combine sinais estatísticos com sinais textuais apenas após filtrar por evidência objetiva.

## Referências

- `docs/catalogo_redflags_score.md` — catálogo completo de sinais e sugestões de peso.
- `docs/dicionario_dados.md` — semântica das tabelas, chaves e red flags por coluna.
- `docs/exemplos_queries.sql` — consulta exemplos para gerar sinais no DuckDB.
