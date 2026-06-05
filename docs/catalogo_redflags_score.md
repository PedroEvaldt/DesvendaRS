# Catalogo de Red Flags e Score de Risco

> **Objetivo:** consolidar as red flags candidatas para um score explicavel de risco.
> Este catalogo usa os dados ja carregados no DuckDB e os percentuais de nulos do
> `docs/inventario_fontes.md` quando disponiveis.

Este documento nao afirma fraude. Cada sinal abaixo deve ser tratado como
**indicio**, **alerta** ou **sinal contextual** que merece revisao humana.

---

## Como Ler Este Catalogo

### Forca do sinal

| Forca | Significado operacional | Pontuacao tipica |
|---|---|---:|
| Forte | Inconsistencia objetiva ou padrao dificil de explicar isoladamente | 20 a 30 |
| Media | Sinal relevante, mas com falsos positivos esperados | 10 a 15 |
| Fraca/contextual | Bom como amplificador, ruim como acusador isolado | 3 a 8 |
| LLM/textual | Requer interpretacao semantica; usar como segunda camada | 5 a 20 |

### Regras recomendadas de score

1. **Capar o score em 100.**
2. **Nao somar `sancionado_historico` quando `sancionado_ativo` tambem acionar** para o mesmo contrato.
3. **Evitar dupla contagem entre `sobrepreco_moderado` e `sobrepreco_alto`**: se alto acionar, moderado nao soma.
4. **Guardar explicabilidade:** o score deve listar quais sinais foram ativados, quais colunas foram usadas e qual evidencia concreta apareceu.
5. **Separar score por escopo:** fornecedor, licitacao, item e orgao podem ter scores diferentes. Um score unico deve combinar esses niveis com cuidado.

### Observacao sobre percentuais de nulos

O inventario atual cobre `licitacao.csv`, `pessoas.csv`, `item.csv`,
`licitante.csv`, `Dados-Empresas-RS.csv`, `Socios-RS.csv`, `CEIS`, `CNEP` e
`CFIL/RS`. As fontes `proposta.csv`, `item_prop.csv` e `evento_lic.csv` ja sao
usadas pelos loaders, mas seus percentuais de nulos **nao aparecem no
`inventario_fontes.md` atual**. Onde essas fontes forem usadas, o campo de nulos
fica marcado como `nao inventariado`.

---

## Fontes e Cobertura Relevante

| Fonte | Colunas importantes | % de nulos no inventario |
|---|---|---|
| `licitacao.csv` | `CD_ORGAO`, `NM_ORGAO`, `NR_LICITACAO`, `ANO_LICITACAO`, `CD_TIPO_MODALIDADE` | 0,0% |
| `licitacao.csv` | `DS_OBJETO` | 0,0% |
| `licitacao.csv` | `VL_LICITACAO` | 1,65% |
| `licitacao.csv` | `DT_ABERTURA` | 0,01% |
| `licitacao.csv` | `DT_HOMOLOGACAO` | 63,19% |
| `licitacao.csv` | `VL_HOMOLOGADO` | 65,98% |
| `licitacao.csv` | `TP_DOCUMENTO_FORNECEDOR`, `NR_DOCUMENTO_FORNECEDOR` | 65,96% |
| `licitacao.csv` | `TP_DOCUMENTO_VENCEDOR`, `NR_DOCUMENTO_VENCEDOR` | 97,94% |
| `licitacao.csv` | `CD_TIPO_FUNDAMENTACAO` | 9,77% |
| `licitacao.csv` | `NR_ARTIGO`, `DS_INCISO`, `DS_LEI` | 95,4%, 96,51%, 95,12% |
| `licitacao.csv` | `DS_OBSERVACAO` | 81,78% |
| `licitacao.csv` | `DS_JUST_PRESENCIAL` | 95,02% |
| `licitacao.csv` | `BL_ORCAMENTO_SIGILOSO` | 77,58% |
| `licitacao.csv` | `BL_COVID19`, `BL_PERMITE_CONSORCIO`, `BL_INVERSAO_FASES` | 0,0% |
| `licitante.csv` | chave da licitacao + `TP_DOCUMENTO`, `NR_DOCUMENTO` | 0,0% |
| `licitante.csv` | `BL_BENEFICIO_MICRO_EPP` | 6,48% |
| `licitante.csv` | `TP_RESULTADO_HABILITACAO` | 95,12% |
| `item.csv` | chave da licitacao + `NR_LOTE`, `NR_ITEM`, `DS_ITEM`, `QT_ITENS`, `SG_UNIDADE_MEDIDA` | 0,0% |
| `item.csv` | `VL_UNITARIO_ESTIMADO`, `VL_TOTAL_ESTIMADO` | 3,26% |
| `item.csv` | `VL_UNITARIO_HOMOLOGADO`, `VL_TOTAL_HOMOLOGADO` | 46,43% |
| `item.csv` | `NR_DOCUMENTO` de fornecedor do item | 71,66% |
| `item.csv` | `CD_FONTE_REFERENCIA`, `DS_FONTE_REFERENCIA` | 78,92%, 77,69% |
| `item.csv` | `BL_COVID19` | 0,0% |
| `Dados-Empresas-RS.csv` | `cnpj`, `razao_social`, `data_abertura`, `cnae`, `capital_social`, `situacao_cadastral`, `porte`, `cep`, `id_municipio` | 0,0% |
| `Dados-Empresas-RS.csv` | `tipo_logradouro`, `bairro` | 1,67%, 1,33% |
| `Socios-RS.csv` | `cnpj`, `tipo_socio`, `qualificacao`, `data_entrada`, `faixa_etaria` | 0,0% |
| `Socios-RS.csv` | `nome_socio`, `doc_socio` | 0,13%, 1,26% |
| `CEIS` | `CPF OU CNPJ DO SANCIONADO`, `CATEGORIA DA SANCAO`, `DATA INICIO SANCAO`, `ORGAO SANCIONADOR` | 0,0% |
| `CEIS` | `DATA FINAL SANCAO` | 8,71% |
| `CNEP` | `CPF OU CNPJ DO SANCIONADO`, `CATEGORIA DA SANCAO`, `VALOR DA MULTA`, `DATA INICIO SANCAO` | 0,0% |
| `CNEP` | `DATA FINAL SANCAO` | 97,49% |
| `CFIL/RS` | colunas numeradas usadas pelo loader de sancoes | variavel; datas principais: 12,47% e 12,68% em colunas 13 e 14 |
| `proposta.csv` | chave da licitacao, `NR_DOCUMENTO`, `DT_PROPOSTA`, `TP_RESULTADO_PROPOSTA`, `VL_TOTAL_PROPOSTA`, `PC_DESCONTO`, `DT_HOMOLOGACAO` | nao inventariado |
| `item_prop.csv` | chave da licitacao + item, `NR_DOCUMENTO`, `VL_UNITARIO`, `VL_TOTAL_ITEM`, `TP_RESULTADO_PROPOSTA`, `TP_RESULTADO_HABILITACAO` | nao inventariado |
| `evento_lic.csv` | chave da licitacao, `SQ_EVENTO`, `CD_TIPO_EVENTO`, `DT_EVENTO`, `DS_PUBLICACAO`, `TP_RESULTADO` | nao inventariado |

---

## Red Flags Automaticas Por Fornecedor

| Sinal | Pontos | Forca | Logica | Fontes/colunas | Nulos relevantes | Observacoes |
|---|---:|---|---|---|---|---|
| `indicio_sancionado_ativo` | +30 | Forte | Fornecedor tem sancao vigente na data do contrato. | `contratos.cnpj_fornecedor`, `contratos.data_contrato`; `sancoes.cnpj`, `data_inicio`, `data_fim`; fontes `CEIS`, `CNEP`, `CFIL/RS`. | CEIS: CNPJ, categoria e inicio 0,0%; fim 8,71%. CNEP: CNPJ, categoria e inicio 0,0%; fim 97,49%. | Usar janela temporal: `data_inicio <= data_contrato <= COALESCE(data_fim, data futura)`. |
| `indicio_sancionado_historico` | +12 | Media | Fornecedor aparece em lista de sancoes em qualquer periodo. | Mesmas colunas de `sancoes` acima. | Mesmos nulos de sancoes. | Nao somar se `indicio_sancionado_ativo` ja acionou no mesmo contrato. |
| `indicio_empresa_inativa_com_contrato` | +22 | Forte | Empresa com situacao cadastral diferente de ativa aparece com contrato recente. | `empresas.situacao_cadastral`, `empresas.cnpj`; `contratos.cnpj_fornecedor`, `data_contrato`. Fonte `Dados-Empresas-RS.csv`. | `situacao_cadastral`, `cnpj`, `data_abertura`: 0,0%. | Precisa definir quais codigos sao ativos/inativos; no dicionario, `2=ativa`, `4=baixada`, `8=inapta`. |
| `indicio_empresa_jovem_contrato_grande` | +10 | Media | Empresa aberta ha menos de 180 dias recebe contrato acima de R$ 100 mil. | `empresas.data_abertura`; `contratos.data_contrato`, `valor_contrato`. | Receita: `data_abertura` 0,0%; `VL_LICITACAO` 1,65%; `VL_HOMOLOGADO` 65,98% na origem. | Melhor quando combinado com capital baixo, baixa competicao ou socios recentes. |
| `indicio_capital_baixo` | +8 | Media | Valor do contrato e mais de 10 vezes o capital social. | `empresas.capital_social`; `contratos.valor_contrato`. | `capital_social` 0,0%; valor licitacao 1,65%; homologado 65,98% na origem. | Capital social pode ser simbolico; nao deve pesar demais sozinho. |
| `indicio_capital_irrisorio_contrato_alto` | +12 | Media | Capital social muito baixo, por exemplo ate R$ 1 mil, com contrato relevante. | `empresas.capital_social`; `contratos.valor_contrato`. | `capital_social` 0,0%; valor licitacao 1,65%; homologado 65,98% na origem. | Mais interpretavel que razao simples quando capital social e zero ou quase zero. |
| `indicio_socio_comum_competidores` | +22 | Forte | Empresas que concorrem na mesma licitacao compartilham o mesmo `doc_socio` mascarado. | `socios.cnpj`, `doc_socio`; `propostas.cnpj_proposta` ou `licitante.NR_DOCUMENTO`; chave da licitacao. | `Socios-RS`: `doc_socio` 1,26%; `licitante` chave e CNPJ 0,0%; `proposta.csv` nao inventariado. | Forte somente quando o socio comum aparece entre competidores da mesma licitacao. |
| `indicio_socio_recente_antes_contrato` | +10 | Media | Socio entrou pouco antes de contrato grande. | `socios.data_entrada`, `socios.cnpj`; `contratos.data_contrato`, `valor_contrato`. | `data_entrada` 0,0%; `doc_socio` 1,26%; valor licitacao 1,65%; homologado 65,98% na origem. | Exigir janela, por exemplo entrada ate 180 dias antes do contrato. |
| `indicio_endereco_compartilhado_competidores` | +12 | Media | Competidores da mesma licitacao possuem mesmo endereco, CEP ou logradouro normalizado. | `empresas.endereco`, `cep`, `municipio`; `propostas` ou `licitante`; chave da licitacao. | Receita: `cep` 0,0%, `logradouro` 0,0%, `tipo_logradouro` 1,67%, `bairro` 1,33%; `proposta.csv` nao inventariado. | Pode ter falso positivo por contadores, coworkings e enderecos rurais. Melhor se combinado com socio comum. |
| `indicio_cartel_recorrente` | +12 | Media | Par de CNPJs concorre junto em 5 ou mais licitacoes. | `propostas.cnpj_proposta`; chave da licitacao. | `proposta.csv` nao inventariado. | Subir peso se tambem houver alternancia de vencedores ou propostas muito proximas. |
| `indicio_rotacao_vencedores` | +20 | Forte | Grupo de CNPJs concorre repetidamente e alterna vencedores entre licitacoes similares. | `propostas.cnpj_proposta`, `valor_total_proposta`, `resultado_proposta`; chave da licitacao; `licitacao.DS_OBJETO`. | `proposta.csv` nao inventariado; `DS_OBJETO` 0,0%. | Uma das melhores flags de conluio quando ha recorrencia e objetos comparaveis. |
| `indicio_segundo_colocado_recorrente` | +15 | Media | O mesmo CNPJ aparece repetidamente como segundo colocado para o mesmo vencedor. | `propostas.valor_total_proposta`, `cnpj_proposta`, `resultado_proposta`; chave da licitacao. | `proposta.csv` nao inventariado. | Forte se ocorre no mesmo orgao ou mesmo tipo de objeto. |
| `indicio_fornecedor_concentrado_por_orgao` | +12 | Media | Fornecedor concentra parcela anormal do gasto de um orgao ou municipio. | `contratos.cnpj_fornecedor`, `orgao`, `municipio`, `valor_contrato`. | `municipio` derivado cobre 89,8%; valor licitacao 1,65%; homologado 65,98% na origem. | Usar percentual por orgao/setor, nao contagem bruta. |
| `indicio_frequencia_empresa_setor_anomala` | +10 | Media | Empresa aparece muito acima do padrao esperado para seu setor/CNAE e tipo de objeto. | `empresas.cnae`; `contratos.objeto`, `cnpj_fornecedor`; `licitacao.DS_OBJETO`; opcional `itens.descricao_normalizada`. | `cnae` 0,0%; `DS_OBJETO` 0,0%; `DS_ITEM` 0,0%. | Normalizar por setor. Frequencia bruta e ruim porque alguns setores sao naturalmente concentrados. |
| `indicio_empresa_fora_do_setor` | +12 | Media | CNAE da empresa parece incompatovel com o objeto ou itens contratados. | `empresas.cnae`; `licitacao.DS_OBJETO`; `item.DS_ITEM`. | `cnae` 0,0%; `DS_OBJETO` 0,0%; `DS_ITEM` 0,0%. | Pode ser regra por palavras-chave ou LLM; como SQL puro, manter peso moderado. |

---

## Red Flags Automaticas Por Licitacao

| Sinal | Pontos | Forca | Logica | Fontes/colunas | Nulos relevantes | Observacoes |
|---|---:|---|---|---|---|---|
| `alerta_competicao_zero` | +22 | Forte | Licitacao tem exatamente uma proposta classificada. | `vw_proposta_unica`; `propostas.resultado_proposta`; chave da licitacao. | `proposta.csv` nao inventariado. | Mais forte que `qtd_participantes=1`, porque considera desclassificacoes. |
| `alerta_baixa_competicao` | +6 | Fraca/contextual | Licitacao tem ate 2 participantes. | `contratos.qtd_participantes`; origem `licitante.csv`. | `licitante` chave e CNPJ 0,0%. | Bom amplificador, fraco sozinho. |
| `alerta_cover_bidding` | +15 | Media | Em licitacao com ao menos 3 propostas classificadas, a segunda menor proposta e muito maior que a menor. | `vw_cover_bidding_indicios`; `propostas.valor_total_proposta`, `resultado_proposta`. | `proposta.csv` nao inventariado. | No catalogo original usa `razao >= 5`; a view inicial calcula a partir de `razao >= 2`. |
| `alerta_dispensa_alto_valor` | +25 | Forte | Modalidade dispensa/inexigibilidade com valor acima do teto legal aplicavel. | `licitacao.CD_TIPO_MODALIDADE`, `VL_LICITACAO`, `VL_HOMOLOGADO`, `CD_TIPO_FUNDAMENTACAO`, `NR_ARTIGO`, `DS_INCISO`, `DS_LEI`. | Modalidade 0,0%; `VL_LICITACAO` 1,65%; `VL_HOMOLOGADO` 65,98%; fundamentacao 9,77%; artigo/inciso/lei acima de 95% nulos. | Precisa manter tabela de tetos e regras legais atualizada. |
| `indicio_fracionamento_dispensa` | +25 | Forte | Varias dispensas/inexigibilidades similares, do mesmo orgao/fornecedor/objeto, em janela curta, cada uma abaixo do teto, mas soma acima do teto. | `licitacao.CD_TIPO_MODALIDADE`, `DS_OBJETO`, `VL_LICITACAO`, `DT_ABERTURA`, `NM_ORGAO`; `contratos.cnpj_fornecedor`. | `DS_OBJETO` 0,0%; `VL_LICITACAO` 1,65%; `DT_ABERTURA` 0,01%; fornecedor direto na origem 65,96% nulo, mas `licitante` tem CNPJ 0,0%. | Flag muito promissora. Requer normalizar objeto e janela temporal, ex. 30/60/90 dias. |
| `indicio_vencedor_recorrente_mesmo_objeto` | +15 | Media | Mesmo fornecedor vence repetidamente objetos parecidos no mesmo orgao. | `contratos.cnpj_fornecedor`, `orgao`, `objeto`; `licitacao.DS_OBJETO`; opcional `itens.descricao_normalizada`. | `DS_OBJETO` 0,0%; `DS_ITEM` 0,0%; valor licitacao 1,65%. | Forte se tambem houver baixa competicao ou dispensa. |
| `indicio_propostas_muito_proximas` | +12 | Media | Propostas classificadas tem dispersao muito baixa, sugerindo combinacao ou preco combinado. | `propostas.valor_total_proposta`, `resultado_proposta`; chave da licitacao. | `proposta.csv` nao inventariado. | Usar coeficiente de variacao baixo e exigir N minimo de propostas. |
| `indicio_desconto_inexistente_em_ambiente_competitivo` | +8 | Fraca/contextual | Ha competicao formal, mas vencedora quase nao reduz o valor estimado. | `propostas.valor_total_proposta`; `licitacao.VL_LICITACAO`; `item.VL_UNITARIO_ESTIMADO`; `item_prop.PC_DESCONTO`. | `VL_LICITACAO` 1,65%; `VL_UNITARIO_ESTIMADO` 3,26%; `proposta.csv` e `item_prop.csv` nao inventariados. | Melhor como complemento de baixa competicao ou propostas muito proximas. |
| `alerta_alteracao_regra_tardia` | +10 | Media | Alteracao ou republicacao de edital ocorre mais de 30 dias apos primeira publicacao. | `vw_alteracao_apos_abertura`; `eventos_licitacao.cd_tipo_evento`, `data_evento`. | `evento_lic.csv` nao inventariado. | Alteracao tardia pode ser legitima; subir peso se ocorrer apos propostas. |
| `indicio_alteracao_edital_beneficia_vencedor` | +20 | Forte | Depois de alteracao/republicacao, muda o conjunto de classificados ou entra o vencedor final. | `eventos_licitacao`; `propostas.data_proposta`, `resultado_proposta`, `cnpj_proposta`; chave da licitacao. | `evento_lic.csv` e `proposta.csv` nao inventariados. | Precisa reconstruir linha do tempo. Pode ser SQL avancado ou LLM com eventos textuais. |
| `alerta_anulacao_historica` | +5 | Fraca/contextual | Mesmo orgao tem historico de anulacoes ou suspensoes. | `eventos_licitacao.cd_tipo_evento` (`ANO`, `SUO`), `cd_orgao`. | `evento_lic.csv` nao inventariado. | Sinal de risco administrativo do orgao, nao necessariamente do fornecedor. |
| `indicio_prazo_curto_publicacao_abertura` | +15 | Media | Prazo entre publicacao do edital e abertura/encerramento e muito curto para a modalidade. | `eventos_licitacao.cd_tipo_evento`, `data_evento`; `licitacao.DT_ABERTURA`, `CD_TIPO_MODALIDADE`. | `DT_ABERTURA` 0,01%; `evento_lic.csv` nao inventariado. | Precisa tabela de prazos legais por modalidade/objeto. |
| `alerta_orcamento_sigiloso_baixa_competicao` | +8 | Fraca/contextual | Orcamento sigiloso combinado com proposta unica ou baixa competicao. | `licitacao.BL_ORCAMENTO_SIGILOSO`; `contratos.qtd_participantes`; `vw_proposta_unica`. | `BL_ORCAMENTO_SIGILOSO` 77,58%; propostas nao inventariadas. | Pela alta nulidade, usar apenas quando preenchido. |

---

## Red Flags Automaticas Por Item ou Preco

| Sinal | Pontos | Forca | Logica | Fontes/colunas | Nulos relevantes | Observacoes |
|---|---:|---|---|---|---|---|
| `alerta_sobrepreco_alto` | +18 | Media/Forte | Item homologado custa ao menos 5 vezes a mediana do grupo `(descricao_normalizada, unidade)`. | `vw_sobrepreco_indicios`; `item.DS_ITEM`, `SG_UNIDADE_MEDIDA`, `VL_UNITARIO_HOMOLOGADO`. | `DS_ITEM` e unidade 0,0%; `VL_UNITARIO_HOMOLOGADO` 46,43%. | Forte quando a descricao e especifica; falso positivo em descricoes genericas. |
| `alerta_sobrepreco_moderado` | +6 | Fraca/Media | Item homologado custa entre 3 e 5 vezes a mediana do grupo. | Mesmas fontes do sobrepreco alto. | Mesmos nulos do sobrepreco alto. | Nao somar se `alerta_sobrepreco_alto` acionar. |
| `alerta_covid_sobrepreco` | +10 | Media | Item ou licitacao COVID tambem apresenta sobrepreco. | `item.BL_COVID19` ou `licitacao.BL_COVID19`; `vw_sobrepreco_indicios`. | `BL_COVID19` em `licitacao` e `item`: 0,0%; homologado item 46,43%. | Bom amplificador, nao substitui a analise de preco. |
| `indicio_preco_estimado_acima_mediana` | +15 | Media/Forte | O valor unitario estimado pelo orgao ja esta muito acima da mediana historica do item. | `item.DS_ITEM`, `SG_UNIDADE_MEDIDA`, `VL_UNITARIO_ESTIMADO`. | `DS_ITEM` e unidade 0,0%; `VL_UNITARIO_ESTIMADO` 3,26%. | Muito promissora porque o estimado tem cobertura melhor que o homologado. |
| `indicio_proposta_item_perdedora_artificialmente_alta` | +12 | Media | Em um mesmo item, propostas perdedoras tem valor unitario muito acima da menor proposta. | `item_prop.VL_UNITARIO`, `VL_TOTAL_ITEM`, `TP_RESULTADO_PROPOSTA`, chave do item e licitacao. | `item_prop.csv` nao inventariado. | Versao granular de cover bidding. |
| `indicio_desclassificacao_conveniente` | +20 | Forte | Proposta mais barata e desclassificada/inabilitada, e vence proposta mais cara. | `propostas_itens.valor_unitario` ou `valor_total_item`, `resultado_proposta`, `resultado_habilitacao`; `propostas.valor_total_proposta`. | `item_prop.csv` e `proposta.csv` nao inventariados; `licitante.TP_RESULTADO_HABILITACAO` tem 95,12% nulos se usar `licitante.csv`. | Forte se houver justificativa fraca para a inabilitacao. |
| `indicio_fonte_referencia_ausente_preco_alto` | +8 | Fraca/contextual | Item com preco alto nao informa fonte de referencia do valor estimado. | `item.CD_FONTE_REFERENCIA`, `DS_FONTE_REFERENCIA`, `VL_UNITARIO_ESTIMADO`, `VL_UNITARIO_HOMOLOGADO`. | Fonte referencia 78,92% e 77,69% nulos; estimado 3,26%; homologado 46,43%. | Alta nulidade torna a flag fraca; util como amplificador de sobrepreco. |

---

## Red Flags Por Orgao ou Padrao Sistemico

| Sinal | Pontos | Forca | Logica | Fontes/colunas | Nulos relevantes | Observacoes |
|---|---:|---|---|---|---|---|
| `indicio_orgao_sobrepreco_recorrente` | +12 | Media | Orgao aparece repetidamente em itens com razao alta contra mediana. | `vw_sobrepreco_indicios`; `contratos.orgao`, `municipio`. | `municipio` cobre 89,8%; homologado item 46,43%. | Score deve ser do orgao, nao do fornecedor. |
| `indicio_orgao_baixa_competicao_recorrente` | +10 | Media | Orgao tem proporcao alta de licitacoes com proposta unica ou ate 2 participantes. | `vw_proposta_unica`; `contratos.qtd_participantes`, `orgao`. | `licitante` chave/CNPJ 0,0%; `proposta.csv` nao inventariado. | Bom para priorizar auditoria em orgaos. |
| `indicio_orgao_dispensas_recorrentes` | +12 | Media | Orgao usa dispensa/inexigibilidade em frequencia ou valor acima do padrao de pares. | `licitacao.CD_TIPO_MODALIDADE`, `VL_LICITACAO`, `NM_ORGAO`, `DT_ABERTURA`. | Modalidade 0,0%; valor 1,65%; data abertura 0,01%. | Comparar com orgaos de porte semelhante. |
| `indicio_fornecedor_exclusivo_orgao` | +10 | Media | Fornecedor praticamente so recebe contratos de um unico orgao. | `contratos.cnpj_fornecedor`, `orgao`, `valor_contrato`; `empresas.cnae`. | Valor licitacao 1,65%; homologado 65,98% na origem. | Pode ser normal em fornecedor local; combinar com baixa competicao. |

---

## Red Flags Para Avaliacao Por LLM

Estas flags podem ate usar pre-filtros SQL, mas a decisao final depende de
interpretacao textual. O ideal e gerar candidatos por regra e pedir ao modelo
uma avaliacao estruturada, com justificativa curta e evidencia citada.

| Sinal | Pontos | Forca | Logica | Fontes/colunas | Nulos relevantes | Observacoes |
|---|---:|---|---|---|---|---|
| `llm_justificativa_inexigibilidade_fraca` | +20 | LLM/textual forte | Avaliar se a justificativa da inexigibilidade/dispensa e concreta, especifica e aderente ao fundamento legal. | `licitacao.CD_TIPO_MODALIDADE`, `CD_TIPO_FUNDAMENTACAO`, `DS_OBSERVACAO`, `DS_OBJETO`, `NR_ARTIGO`, `DS_INCISO`, `DS_LEI`; possivel documento externo via `LINK_LICITACON_CIDADAO`. | `DS_OBJETO` 0,0%; fundamentacao 9,77%; `DS_OBSERVACAO` 81,78%; artigo/inciso/lei acima de 95%; link 0,0%. | Forte quando ha texto suficiente. Se a justificativa nao estiver no CSV, precisa buscar documento externo. |
| `llm_objeto_vago_ou_direcionado` | +12 | LLM/textual media | Detectar objeto generico demais ou com requisitos que parecem favorecer fornecedor especifico. | `licitacao.DS_OBJETO`; `item.DS_ITEM`; `eventos.descricao_publicacao`. | `DS_OBJETO` 0,0%; `DS_ITEM` 0,0%; `evento_lic.csv` nao inventariado. | Bom complemento para dispensa, inexigibilidade e baixa competicao. |
| `llm_cnae_incompativel_objeto` | +15 | LLM/textual media | Comparar semanticamente CNAE da empresa com objeto/itens contratados. | `empresas.cnae`; `licitacao.DS_OBJETO`; `item.DS_ITEM`; opcional `pessoas.DS_OBJETO_SOCIAL`. | `cnae` 0,0%; `DS_OBJETO` 0,0%; `DS_ITEM` 0,0%; `DS_OBJETO_SOCIAL` 96,39%. | Melhor que regra por palavra-chave, mas precisa retornar explicacao. |
| `llm_fracionamento_semantico_objetos` | +20 | LLM/textual forte | Identificar objetos semanticamente iguais ou complementares em dispensas proximas, mesmo com descricoes diferentes. | `licitacao.DS_OBJETO`, `DT_ABERTURA`, `VL_LICITACAO`, `CD_TIPO_MODALIDADE`, `NM_ORGAO`; `contratos.cnpj_fornecedor`. | `DS_OBJETO` 0,0%; `DT_ABERTURA` 0,01%; `VL_LICITACAO` 1,65%. | Versao semantica do `indicio_fracionamento_dispensa`. |
| `llm_alteracao_edital_direcionadora` | +18 | LLM/textual forte | Ler descricao/publicacao de alteracoes e avaliar se a mudanca restringe competicao ou favorece perfil especifico. | `eventos_licitacao.cd_tipo_evento`, `descricao_publicacao`, `data_evento`; `propostas`. | `evento_lic.csv` e `proposta.csv` nao inventariados. | Usar principalmente em eventos `AED` e `REE`. |
| `llm_impugnacao_indica_restricao` | +15 | LLM/textual media | Interpretar impugnacoes/esclarecimentos para detectar denuncia de exigencia restritiva. | `eventos_licitacao.cd_tipo_evento` (`IME`, `ESC`), `descricao_publicacao`, `tipo_resultado`. | `evento_lic.csv` nao inventariado. | O modelo deve diferenciar impugnacao procedente de mero questionamento. |
| `llm_item_generico_incomparavel` | -5 ou bloqueio | Controle de qualidade | Avaliar se a descricao do item e generica demais para entrar em comparacao de sobrepreco. | `item.DS_ITEM`, `SG_UNIDADE_MEDIDA`, `descricao_normalizada`. | `DS_ITEM` e unidade 0,0%. | Pode reduzir ou bloquear pontuacao de sobrepreco quando a comparacao for ruim. |
| `llm_preco_plausivel_pelo_contexto` | -10 a +10 | LLM/textual contextual | Avaliar se preco aparentemente alto pode ser explicado por quantidade, unidade, especificacao, urgencia ou escopo. | `item.DS_ITEM`, `QT_ITENS`, `SG_UNIDADE_MEDIDA`, valores estimado/homologado, `licitacao.DS_OBJETO`. | `QT_ITENS`, unidade e descricao 0,0%; estimado 3,26%; homologado 46,43%. | Deve ajustar score, nao substituir regra estatistica. |
| `llm_texto_copiado_entre_editais` | +8 | LLM/textual contextual | Detectar objetos/justificativas muito semelhantes entre orgaos ou processos diferentes. | `licitacao.DS_OBJETO`, `DS_OBSERVACAO`, documentos externos. | `DS_OBJETO` 0,0%; `DS_OBSERVACAO` 81,78%; link 0,0%. | Pode indicar padrao de fornecedor/modelo, mas tambem uso legitimo de minuta padrao. |
| `llm_resumo_explicabilidade_score` | 0 | Apoio | Gerar explicacao do score com evidencias e ressalvas. | Todas as flags acionadas e colunas usadas. | Depende das flags. | Nao pontua; serve para auditoria e interface do usuario. |

---

## Sugestao De Pesos Consolidados

### Pesos altos, bons candidatos para primeira versao do score

| Sinal | Pontos sugeridos |
|---|---:|
| `indicio_sancionado_ativo` | +30 |
| `alerta_dispensa_alto_valor` | +25 |
| `indicio_fracionamento_dispensa` | +25 |
| `indicio_empresa_inativa_com_contrato` | +22 |
| `indicio_socio_comum_competidores` | +22 |
| `alerta_competicao_zero` | +22 |
| `indicio_rotacao_vencedores` | +20 |
| `indicio_desclassificacao_conveniente` | +20 |
| `indicio_alteracao_edital_beneficia_vencedor` | +20 |

### Pesos medios, bons como composicao

| Sinal | Pontos sugeridos |
|---|---:|
| `alerta_sobrepreco_alto` | +18 |
| `alerta_cover_bidding` | +15 |
| `indicio_vencedor_recorrente_mesmo_objeto` | +15 |
| `indicio_segundo_colocado_recorrente` | +15 |
| `indicio_preco_estimado_acima_mediana` | +15 |
| `indicio_prazo_curto_publicacao_abertura` | +15 |
| `indicio_empresa_fora_do_setor` | +12 |
| `indicio_capital_irrisorio_contrato_alto` | +12 |
| `indicio_endereco_compartilhado_competidores` | +12 |
| `indicio_cartel_recorrente` | +12 |
| `indicio_fornecedor_concentrado_por_orgao` | +12 |
| `indicio_orgao_sobrepreco_recorrente` | +12 |
| `indicio_orgao_dispensas_recorrentes` | +12 |

### Pesos baixos ou contextuais

| Sinal | Pontos sugeridos |
|---|---:|
| `indicio_sancionado_historico` | +12 |
| `indicio_empresa_jovem_contrato_grande` | +10 |
| `indicio_socio_recente_antes_contrato` | +10 |
| `indicio_frequencia_empresa_setor_anomala` | +10 |
| `indicio_orgao_baixa_competicao_recorrente` | +10 |
| `indicio_fornecedor_exclusivo_orgao` | +10 |
| `alerta_covid_sobrepreco` | +10 |
| `indicio_capital_baixo` | +8 |
| `indicio_desconto_inexistente_em_ambiente_competitivo` | +8 |
| `alerta_orcamento_sigiloso_baixa_competicao` | +8 |
| `indicio_fonte_referencia_ausente_preco_alto` | +8 |
| `alerta_sobrepreco_moderado` | +6 |
| `alerta_baixa_competicao` | +6 |
| `alerta_anulacao_historica` | +5 |

---

## Priorizacao De Implementacao

| Prioridade | Sinais | Motivo |
|---|---|---|
| P0 | `sancionado_ativo`, `empresa_inativa`, `competicao_zero`, `dispensa_alto_valor`, `fracionamento_dispensa`, `sobrepreco_alto`, `preco_estimado_acima_mediana` | Usam colunas com boa cobertura ou views ja existentes; alto valor explicativo. |
| P1 | `socio_comum_competidores`, `rotacao_vencedores`, `segundo_colocado_recorrente`, `desclassificacao_conveniente`, `cover_bidding` | Bons sinais de conluio; dependem de `proposta.csv`/`item_prop.csv`, que precisam entrar no inventario de nulos. |
| P2 | `alteracao_regra_tardia`, `alteracao_edital_beneficia_vencedor`, `prazo_curto_publicacao_abertura`, `anulacao_historica` | Dependem da linha do tempo de `evento_lic.csv`; bons para score por licitacao/orgao. |
| P3 | flags LLM | Devem vir depois de filtros SQL para reduzir custo e melhorar precisao. |

---

## Lacunas Tecnicas Para Melhorar O Score

1. **Atualizar `docs/inventario_fontes.md` com `proposta.csv`, `item_prop.csv` e `evento_lic.csv`.**
2. **Preservar a chave composta da licitacao em `contratos`.** Hoje o dicionario indica que `contratos` perdeu essa chave, o que dificulta cruzar contrato diretamente com item/proposta/evento.
3. **Criar tabela auxiliar de tetos legais por modalidade, ano e fundamento.**
4. **Criar normalizadores de objeto e setor:** objeto normalizado, grupo de compra e mapa CNAE -> categorias de fornecimento.
5. **Separar score por contrato, fornecedor, licitacao, item e orgao.** Misturar tudo em um unico numero sem escopo claro reduz explicabilidade.

