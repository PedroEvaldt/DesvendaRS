"""Tests for the Streamlit app query helpers that do not require a real DB."""
from __future__ import annotations

from app.db import DatabaseStatus
from app.queries import ContractFilters, has_score_view


def test_detecta_view_de_score_quando_disponivel(tmp_path):
    status = DatabaseStatus(
        path=tmp_path / "dados.duckdb",
        exists=True,
        tables={"contratos"},
        views={"vw_score_contratos"},
    )
    assert has_score_view(status)


def test_nao_detecta_view_de_score_quando_ausente(tmp_path):
    status = DatabaseStatus(
        path=tmp_path / "dados.duckdb",
        exists=True,
        tables={"contratos"},
        views={"vw_contratos_com_sancao"},
    )
    assert not has_score_view(status)


def test_contract_filters_defaults_are_non_restrictive():
    filters = ContractFilters()
    assert filters.municipio is None
    assert filters.orgao is None
    assert filters.busca is None
    assert filters.minimo_valor is None
    assert filters.apenas_covid is False
