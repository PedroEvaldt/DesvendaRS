"""Generate a lightweight Markdown dossier for export from the app."""
from __future__ import annotations

import pandas as pd


def render_markdown(detail: dict[str, pd.DataFrame]) -> str:
    """Build a concise dossier from detail data frames."""
    contrato = _first_row(detail.get("contrato"))
    empresa = _first_row(detail.get("empresa"))
    if not contrato:
        return "# Dossie DesvendaRS\n\nContrato nao encontrado.\n"

    lines = [
        "# Dossie DesvendaRS",
        "",
        "> Documento de apoio. Os sinais abaixo sao indicios para revisao humana, nao conclusoes de irregularidade.",
        "",
        "## Contrato",
        f"- Fornecedor: {contrato.get('razao_social') or 'Nao informado'}",
        f"- CNPJ: {contrato.get('cnpj_fornecedor') or 'Nao informado'}",
        f"- Orgao: {contrato.get('orgao') or 'Nao informado'}",
        f"- Municipio: {contrato.get('municipio') or 'Nao informado'}",
        f"- Valor: {_money(contrato.get('valor_contrato'))}",
        f"- Data: {contrato.get('data_contrato') or 'Nao informada'}",
        f"- Numero/processo: {contrato.get('numero_contrato') or 'Nao informado'}",
        "",
    ]

    if empresa:
        lines.extend(
            [
                "## Empresa",
                f"- Situacao cadastral: {empresa.get('situacao_cadastral') or 'Nao informada'}",
                f"- Data de abertura: {empresa.get('data_abertura') or 'Nao informada'}",
                f"- CNAE: {empresa.get('cnae') or 'Nao informado'}",
                f"- Capital social: {_money(empresa.get('capital_social'))}",
                "",
            ]
        )

    lines.extend(_table_section("Sancoes", detail.get("sancoes")))
    lines.extend(_table_section("Socios", detail.get("socios")))
    lines.extend(_table_section("Indicios de sobrepreco", detail.get("sobrepreco")))
    return "\n".join(lines).strip() + "\n"


def _first_row(df: pd.DataFrame | None) -> dict | None:
    if df is None or df.empty:
        return None
    return df.iloc[0].to_dict()


def _table_section(title: str, df: pd.DataFrame | None) -> list[str]:
    if df is None or df.empty:
        return [f"## {title}", "Nenhum registro encontrado.", ""]
    return [f"## {title}", _markdown_table(df.head(20)), ""]


def _markdown_table(df: pd.DataFrame) -> str:
    headers = [str(col) for col in df.columns]
    rows = [["" if pd.isna(value) else str(value) for value in row] for row in df.to_numpy()]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def _money(value: object) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "Nao informado"
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return str(value)
