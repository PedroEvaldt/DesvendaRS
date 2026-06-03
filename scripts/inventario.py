"""Gera docs/inventario_fontes.md inspecionando cada CSV de data/raw/.

Para cada arquivo: detecta encoding e separador, lista colunas reais, mostra
3 amostras e calcula % de nulos nas colunas-chave (CNPJ/data/valor) em uma
amostra de até 50 000 linhas.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

AMOSTRA = 50_000


def detectar_encoding(path: Path) -> str:
    """Tenta utf-8 primeiro; se quebrar, cai para cp1252 (padrão Portal da Transparência)."""
    try:
        with open(path, encoding="utf-8") as f:
            f.read(4096)
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "cp1252"


def detectar_sep(path: Path, encoding: str) -> str:
    with open(path, encoding=encoding) as f:
        primeira = f.readline()
    if primeira.count(";") > primeira.count(","):
        return ";"
    return ","


def inspecionar(path: Path, sem_header: bool = False) -> dict[str, Any]:
    enc = detectar_encoding(path)
    sep = detectar_sep(path, enc)
    kwargs: dict[str, Any] = {
        "sep": sep,
        "encoding": enc,
        "dtype": str,
        "nrows": AMOSTRA,
        "on_bad_lines": "skip",
        "engine": "python",
    }
    if sem_header:
        kwargs["header"] = None
    df = pd.read_csv(path, **kwargs)
    colunas = [str(c) for c in df.columns]
    nulos_pct = {str(c): round(df[c].isna().mean() * 100, 2) for c in df.columns}
    amostras = df.head(3).to_dict(orient="records")
    return {
        "path": path,
        "encoding": enc,
        "sep": repr(sep),
        "linhas_amostradas": len(df),
        "colunas": colunas,
        "nulos_pct": nulos_pct,
        "amostras": amostras,
    }


FONTES = [
    ("LicitaCon — licitacao", config.CSV_LICITACAO, False),
    ("LicitaCon — pessoas", config.CSV_PESSOAS, False),
    ("LicitaCon — item", config.CSV_ITEM, False),
    ("LicitaCon — licitante", config.CSV_LICITANTE, False),
    ("Receita — Empresas RS", config.CSV_EMPRESAS, False),
    ("Receita — Sócios RS", config.CSV_SOCIOS, False),
    ("Sanções — CEIS", config.CSV_CEIS, False),
    ("Sanções — CNEP", config.CSV_CNEP, False),
    ("Sanções — CFIL/RS", config.CSV_CFIL, True),
]


def formatar_md(rel: list[dict[str, Any]]) -> str:
    linhas = [
        "# Inventário das fontes de dados",
        "",
        f"> Gerado automaticamente por `scripts/inventario.py` a partir de `{config.DATA_RAW}`.",
        f"> Amostra de até {AMOSTRA:,} linhas por arquivo.".replace(",", "."),
        "",
    ]
    for r in rel:
        linhas += [
            f"## {r['titulo']}",
            "",
            f"- **Arquivo:** `{r['path'].name}`",
            f"- **Tamanho:** {r['tamanho_mb']:.1f} MB",
            f"- **Encoding detectado:** `{r['encoding']}`",
            f"- **Separador detectado:** `{r['sep']}`",
            f"- **Linhas amostradas:** {r['linhas_amostradas']:,}".replace(",", "."),
            "",
            "**Colunas (nome real → % nulos na amostra):**",
            "",
        ]
        for c in r["colunas"]:
            linhas.append(f"- `{c}` — {r['nulos_pct'][c]}% nulos")
        linhas += ["", "**Primeiras linhas:**", "", "```"]
        for a in r["amostras"]:
            linhas.append(str(a)[:500])
        linhas += ["```", ""]
    return "\n".join(linhas)


def main() -> None:
    relatorio = []
    for titulo, path, sem_header in FONTES:
        if not path.exists():
            print(f"[SKIP] {titulo}: {path} não existe")
            continue
        print(f"[OK]   {titulo}: {path.name}")
        info = inspecionar(path, sem_header=sem_header)
        info["titulo"] = titulo
        info["tamanho_mb"] = path.stat().st_size / 1024 / 1024
        relatorio.append(info)

    md = formatar_md(relatorio)
    destino = config.RAIZ / "docs" / "inventario_fontes.md"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(md, encoding="utf-8")
    print(f"\nInventário escrito em {destino}")


if __name__ == "__main__":
    main()
