"""Demo-first Streamlit interface for DesvendaRS."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import dossier, queries
from app.db import connect, inspect_database
from app.queries import ContractFilters
from app.ui import (
    configure_page,
    format_dataframe,
    metric_row,
    percent_level,
    show_missing_database,
    show_relation_warning,
    signal_strip,
)


REQUIRED_RELATIONS = {
    "contratos",
    "empresas",
    "socios",
    "sancoes",
}


def main() -> None:
    configure_page()
    status = inspect_database()

    if not status.exists:
        show_missing_database(status.path)
        _show_redflag_preview()
        return

    missing = REQUIRED_RELATIONS.difference(status.tables)
    if missing:
        show_relation_warning(missing)
        return

    with connect(status.path) as con:
        st.title("DesvendaRS")
        st.caption("Fila de revisão humana baseada em indícios. Os sinais abaixo não são conclusões de irregularidade.")

        page = st.sidebar.radio(
            "Navegação",
            ["Visão geral", "Fila de revisão"],
            label_visibility="collapsed",
        )

        if page == "Visão geral":
            _overview_page(con, status)
        else:
            _review_queue_page(con, status, ContractFilters())


def _sidebar_filters(options: dict[str, list[str]]) -> ContractFilters:
    st.sidebar.header("Filtros")
    municipio = st.sidebar.selectbox("Município", ["Todos"] + options["municipios"])
    orgao = st.sidebar.selectbox("Órgão", ["Todos"] + options["orgaos"])
    busca = st.sidebar.text_input("Fornecedor, CNPJ ou objeto")
    minimo_valor = st.sidebar.number_input("Valor mínimo", min_value=0.0, step=10_000.0)
    apenas_covid = st.sidebar.checkbox("Apenas COVID-19")
    return ContractFilters(
        municipio=None if municipio == "Todos" else municipio,
        orgao=None if orgao == "Todos" else orgao,
        busca=busca.strip() or None,
        minimo_valor=minimo_valor,
        apenas_covid=apenas_covid,
    )


def _overview_page(con, status) -> None:
    metric_row(queries.overview(con, status))
    st.subheader("Sinais disponíveis por escopo")
    signal_strip(queries.redflag_counts(con, status))

    st.subheader("Contratos homologados para abrir a investigação")
    queue = queries.risk_queue(con, status, ContractFilters(), limit=20)
    if queue.empty:
        st.info("Nenhum contrato encontrado com os dados atuais.")
        return
    display_cols = _queue_display_columns(queue)
    st.dataframe(format_dataframe(queue[display_cols]), use_container_width=True, hide_index=True)


def _review_queue_page(con, status, filters: ContractFilters) -> None:
    queue = queries.risk_queue(con, status, filters, limit=250)
    st.subheader("Fila de revisão")
    if queries.has_score_view(status):
        st.caption("Usando a view de score fornecida pela trilha de análise.")
    else:
        st.caption(
            "Usando score provisório derivado de sanções, cadastro da empresa, baixa competição e sobrepreço."
        )

    if queue.empty:
        st.info("Nenhum contrato encontrado para os filtros atuais.")
        return

    queue = queue.reset_index(drop=True)
    display_cols = _queue_display_columns(queue)
    selected = st.dataframe(
        format_dataframe(queue[display_cols]),
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
    )
    row_index = selected.selection.rows[0] if selected.selection.rows else 0
    row = queue.iloc[row_index]
    score_col = "score_risco" if "score_risco" in queue.columns else "score_provisorio"
    st.markdown(f"**Caso selecionado:** {row.get('razao_social') or row.get('cnpj_fornecedor')}")
    st.caption(percent_level(row.get(score_col)))
    _detail_tabs(con, status, row)


def _detail_tabs(con, status, row: pd.Series) -> None:
    detail = queries.contract_detail(
        con,
        status,
        str(row["cnpj_fornecedor"]),
        None if pd.isna(row.get("numero_contrato")) else str(row.get("numero_contrato")),
    )
    tabs = st.tabs(["Resumo", "Empresa e sócios", "Sanções", "Itens e preço", "Propostas", "Dossiê"])

    with tabs[0]:
        contrato = detail["contrato"]
        if contrato.empty:
            st.info("Contrato não encontrado.")
        else:
            st.dataframe(format_dataframe(contrato), use_container_width=True, hide_index=True)
        _signal_explanation(row)

    with tabs[1]:
        st.write("Empresa")
        st.dataframe(format_dataframe(detail["empresa"]), use_container_width=True, hide_index=True)
        st.write("Sócios")
        st.dataframe(detail["socios"], use_container_width=True, hide_index=True)

    with tabs[2]:
        if detail["sancoes"].empty:
            st.info("Nenhuma sanção encontrada para este CNPJ nas fontes carregadas.")
        else:
            st.dataframe(detail["sancoes"], use_container_width=True, hide_index=True)

    with tabs[3]:
        if not detail["sobrepreco"].empty:
            st.write("Indícios de sobrepreço")
            st.dataframe(format_dataframe(detail["sobrepreco"]), use_container_width=True, hide_index=True)
        st.write("Itens relacionados ao fornecedor")
        st.dataframe(format_dataframe(detail["itens"]), use_container_width=True, hide_index=True)

    with tabs[4]:
        if detail["propostas"].empty:
            st.info("Nenhuma proposta encontrada para este CNPJ nas fontes carregadas.")
        else:
            st.dataframe(format_dataframe(detail["propostas"]), use_container_width=True, hide_index=True)

    with tabs[5]:
        md = dossier.render_markdown(detail)
        st.download_button(
            "Baixar dossiê Markdown",
            md,
            file_name=f"dossie_{row['cnpj_fornecedor']}.md",
            mime="text/markdown",
        )
        st.code(md, language="markdown")


def _signal_explanation(row: pd.Series) -> None:
    signals = []
    if bool(row.get("indicio_sancionado_ativo", False)):
        signals.append("Fornecedor com sanção vigente na data do contrato.")
    elif row.get("qtd_sancoes", 0):
        signals.append("Fornecedor aparece historicamente em lista de sanções.")
    if row.get("qtd_participantes") is not None and row.get("qtd_participantes") <= 2:
        signals.append("Baixa competição registrada na licitação.")
    if bool(row.get("indicio_empresa_inativa_com_contrato", False)):
        signals.append("Situação cadastral da empresa não aparece como ativa no cadastro carregado.")
    if bool(row.get("indicio_empresa_jovem_contrato_grande", False)):
        signals.append("Empresa aberta há menos de 180 dias recebeu contrato acima de R$ 100 mil.")
    if bool(row.get("indicio_capital_baixo", False)):
        signals.append("Valor do contrato é mais de 10 vezes o capital social declarado.")
    if row.get("maior_razao_sobrepreco") is not None and not pd.isna(row.get("maior_razao_sobrepreco")):
        signals.append(f"Item relacionado com razão até {row.get('maior_razao_sobrepreco'):.1f}x contra a mediana.")
    if bool(row.get("flag_covid", False)):
        signals.append("Contrato marcado como COVID-19.")

    if not signals:
        st.info("Nenhum sinal automático forte foi identificado no score provisório.")
        return
    for signal in signals:
        st.markdown(f"<div class='signal'>{signal}</div>", unsafe_allow_html=True)


def _licitation_signals_page(con, status) -> None:
    st.subheader("Sinais por licitação")
    st.caption(
        "Estas views usam a chave composta de licitação. Como `contratos` não preserva essa chave, "
        "elas aparecem como painéis próprios até Pessoa 2 consolidar o score."
    )
    data = queries.licitation_signals(con, status)
    if not data:
        st.info("Nenhuma view de sinal por licitação está disponível no banco atual.")
        return
    for title, df in data.items():
        with st.expander(title, expanded=True):
            st.dataframe(format_dataframe(df), use_container_width=True, hide_index=True)


def _queue_display_columns(df: pd.DataFrame) -> list[str]:
    preferred = [
        "score_risco",
        "score_provisorio",
        "nivel_risco",
        "razao_social",
        "cnpj_fornecedor",
        "municipio",
        "orgao",
        "valor_contrato",
        "data_contrato",
        "qtd_participantes",
        "qtd_sancoes",
        "situacao_cadastral",
        "capital_social",
        "maior_razao_sobrepreco",
    ]
    return [col for col in preferred if col in df.columns]


def _show_redflag_preview() -> None:
    st.subheader("Vocabulário de sinais já definido")
    st.markdown(
        """
        - `indicio_sancionado_ativo`
        - `alerta_competicao_zero`
        - `alerta_sobrepreco_alto`
        - `alerta_cover_bidding`
        - `alerta_alteracao_regra_tardia`
        """
    )


if __name__ == "__main__":
    main()
