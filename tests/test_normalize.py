"""Testes de etl/normalize.py — núcleo crítico do pipeline."""
from __future__ import annotations

from datetime import date

import pytest

from etl.normalize import (
    limpar_cnpj,
    limpar_valor,
    normalizar_texto,
    padronizar_data,
)


class TestLimparCnpj:
    def test_formato_com_pontuacao(self):
        assert limpar_cnpj("12.345.678/0001-95") == "12345678000195"

    def test_ja_limpo(self):
        assert limpar_cnpj("12345678000195") == "12345678000195"

    def test_com_zeros_a_esquerda_perdidos(self):
        assert limpar_cnpj("345678000195") == "00345678000195"

    def test_pouquissimos_digitos(self):
        assert limpar_cnpj("123") == "00000000000123"

    def test_muito_grande_invalido(self):
        assert limpar_cnpj("123456789012345") is None

    def test_so_lixo(self):
        assert limpar_cnpj("abc") is None

    def test_vazio(self):
        assert limpar_cnpj("") is None

    def test_so_espacos(self):
        assert limpar_cnpj("   ") is None

    def test_none(self):
        assert limpar_cnpj(None) is None

    def test_nan_pandas(self):
        assert limpar_cnpj(float("nan")) is None

    def test_inteiro(self):
        assert limpar_cnpj(12345678000195) == "12345678000195"


class TestPadronizarData:
    def test_iso(self):
        assert padronizar_data("2025-05-01") == date(2025, 5, 1)

    def test_iso_com_hora(self):
        assert padronizar_data("2025-05-01 14:30:00") == date(2025, 5, 1)

    def test_br(self):
        assert padronizar_data("01/05/2025") == date(2025, 5, 1)

    def test_br_com_hora(self):
        assert padronizar_data("01/05/2025 14:30") == date(2025, 5, 1)

    def test_data_invalida_formato(self):
        assert padronizar_data("31/02/2025") is None

    def test_data_zero(self):
        assert padronizar_data("0000-00-00") is None

    def test_ano_muito_antigo(self):
        assert padronizar_data("1700-01-01") is None

    def test_ano_muito_no_futuro(self):
        assert padronizar_data("3000-01-01") is None

    def test_vazio(self):
        assert padronizar_data("") is None

    def test_none(self):
        assert padronizar_data(None) is None

    def test_objeto_date_passa(self):
        assert padronizar_data(date(2025, 5, 1)) == date(2025, 5, 1)


class TestLimparValor:
    def test_brasileiro_com_rs(self):
        assert limpar_valor("R$ 1.234,56") == 1234.56

    def test_brasileiro_so_virgula(self):
        assert limpar_valor("1234,56") == 1234.56

    def test_americano(self):
        assert limpar_valor("1234.56") == 1234.56

    def test_inteiro_em_string(self):
        assert limpar_valor("1000") == 1000.0

    def test_milhar_grande(self):
        assert limpar_valor("R$ 12.345.678,90") == 12345678.90

    def test_vazio(self):
        assert limpar_valor("") is None

    def test_none(self):
        assert limpar_valor(None) is None

    def test_lixo(self):
        assert limpar_valor("abc") is None

    def test_float_direto(self):
        assert limpar_valor(1234.56) == 1234.56

    def test_negativo(self):
        assert limpar_valor("-50,25") == -50.25


class TestNormalizarTexto:
    def test_trim(self):
        assert normalizar_texto("  empresa  ") == "empresa"

    def test_colapsa_espacos(self):
        assert normalizar_texto("EMPRESA    XYZ   LTDA") == "EMPRESA XYZ LTDA"

    def test_upper(self):
        assert normalizar_texto("empresa xyz", upper=True) == "EMPRESA XYZ"

    def test_vazio(self):
        assert normalizar_texto("") is None

    def test_so_espacos(self):
        assert normalizar_texto("    ") is None

    def test_none(self):
        assert normalizar_texto(None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
