"""Funções puras de normalização — base de todo cruzamento entre fontes.

A função mais crítica é :func:`limpar_cnpj`: todos os JOINs entre LicitaCon, Receita
e listas de sanção dependem dela. As demais (data, valor, texto) padronizam formatos
heterogêneos (BR vs ISO, vírgula vs ponto decimal, etc.) para tipos Python nativos.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

_NAO_DIGITO = re.compile(r"\D+")
_ESPACOS = re.compile(r"\s+")

_LIMITE_ANO_MIN = 1900
_LIMITE_ANO_MAX = date.today().year + 10

_FORMATOS_DATA = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y",
)


def _eh_nulo(valor: Any) -> bool:
    """True para None, NaN, string vazia ou só-espaços."""
    if valor is None:
        return True
    if isinstance(valor, float) and valor != valor:
        return True
    if isinstance(valor, str) and valor.strip() == "":
        return True
    return False


def limpar_cnpj(valor: Any) -> str | None:
    """Normaliza um CNPJ para 14 dígitos sem pontuação.

    Remove tudo que não é dígito, descarta valores com mais de 14 dígitos (provável
    erro de origem) e completa com zeros à esquerda quando o número de dígitos vem
    truncado (caso comum quando o campo é numérico na fonte e perde o zero líder).
    Retorna ``None`` se o valor for nulo ou não tiver dígito algum.
    """
    if _eh_nulo(valor):
        return None
    so_digitos = _NAO_DIGITO.sub("", str(valor))
    if not so_digitos:
        return None
    if len(so_digitos) > 14:
        return None
    return so_digitos.zfill(14)


def padronizar_data(valor: Any) -> date | None:
    """Converte valor textual em :class:`datetime.date`.

    Aceita formatos ISO (``YYYY-MM-DD``), brasileiros (``DD/MM/YYYY``) e variantes
    com hora. Datas fora da janela ``[1900, hoje+10anos]`` viram ``None`` (são
    quase sempre digitação errada na fonte).
    """
    if _eh_nulo(valor):
        return None
    if isinstance(valor, date) and not isinstance(valor, datetime):
        d = valor
    elif isinstance(valor, datetime):
        d = valor.date()
    else:
        texto = str(valor).strip()
        d = None
        for fmt in _FORMATOS_DATA:
            try:
                d = datetime.strptime(texto, fmt).date()
                break
            except ValueError:
                continue
        if d is None:
            return None
    if d.year < _LIMITE_ANO_MIN or d.year > _LIMITE_ANO_MAX:
        return None
    return d


def limpar_valor(valor: Any) -> float | None:
    """Converte texto monetário para ``float``.

    Trata os dois padrões mais comuns nas fontes:
    * brasileiro com ``R$``, ponto de milhar e vírgula decimal (``"R$ 1.234,56"``);
    * americano simples com ponto decimal (``"1234.56"``).
    Retorna ``None`` para vazio, lixo ou valor não-numérico.
    """
    if _eh_nulo(valor):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    texto = texto.replace("R$", "").replace("r$", "").strip()
    if not texto:
        return None
    tem_virgula = "," in texto
    tem_ponto = "." in texto
    if tem_virgula and tem_ponto:
        # padrão BR: ponto é separador de milhar, vírgula é decimal
        texto = texto.replace(".", "").replace(",", ".")
    elif tem_virgula:
        # só vírgula → decimal BR
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def normalizar_texto(valor: Any, *, upper: bool = False) -> str | None:
    """Limpa texto: trim, colapsa espaços múltiplos, opcionalmente uppercase.

    Útil para razões sociais e nomes de órgão, onde a mesma entidade aparece com
    espaços extras ou caixa diferente.
    """
    if _eh_nulo(valor):
        return None
    texto = _ESPACOS.sub(" ", str(valor)).strip()
    if not texto:
        return None
    return texto.upper() if upper else texto
