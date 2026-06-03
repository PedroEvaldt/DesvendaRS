"""Caminhos relativos das fontes e do banco gerado.

Centraliza paths para que nenhum loader ou teste use caminho absoluto.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

DATA_RAW = RAIZ / "data" / "raw"
DATA_PROCESSED = RAIZ / "data" / "processed"
DB_DIR = RAIZ / "db"
DB_PATH = DB_DIR / "dados.duckdb"

CSV_LICITACAO = DATA_RAW / "licitacao.csv"
CSV_PESSOAS = DATA_RAW / "pessoas.csv"
CSV_ITEM = DATA_RAW / "item.csv"
CSV_LICITANTE = DATA_RAW / "licitante.csv"

CSV_EMPRESAS = DATA_RAW / "Dados-Empresas-RS.csv"
CSV_SOCIOS = DATA_RAW / "Socios-RS.csv"

CSV_CEIS = DATA_RAW / "20260603_CEIS.csv"
CSV_CNEP = DATA_RAW / "20260603_CNEP.csv"
CSV_CFIL = DATA_RAW / "SancoesCFIL-RS.csv"
