"""Baixa e extrai automaticamente as fontes públicas usadas pelo ETL.

Uso rápido:
  uv run python scripts/baixar_fontes.py --ano 2026
  uv run python scripts/baixar_fontes.py --ano 2026 --data-ceis 20260606 --data-cnep 20260606
"""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config

log = logging.getLogger(__name__)

CKAN_URL = "https://dados.tce.rs.gov.br/api/3/action/package_search"
PORTAL_CEIS_URL = "https://portaldatransparencia.gov.br/download-de-dados/ceis"
PORTAL_CNEP_URL = "https://portaldatransparencia.gov.br/download-de-dados/cnep"
FALLBACK_PORTAL_DATA = "20260606"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Baixa fontes públicas para o ETL")
    parser.add_argument("--ano", type=int, default=date.today().year, help="Ano dos dados do TCE-RS a baixar")
    parser.add_argument("--data-ceis", type=str, default=None, help="Data no formato YYYYMMDD para CEIS (ex.: 20260606)")
    parser.add_argument("--data-cnep", type=str, default=None, help="Data no formato YYYYMMDD para CNEP")
    parser.add_argument(
        "--cfil-url",
        type=str,
        default=None,
        help="URL direta ou caminho local do arquivo CFIL/RS (ex.: --cfil-url data/raw/SancoesCFIL-RS.csv)",
    )
    parser.add_argument("--saida", type=Path, default=config.DATA_RAW, help="Diretório onde salvar os arquivos extraídos")
    parser.add_argument("--listar", action="store_true", help="Apenas lista as URLs descobertas, sem baixar")
    parser.add_argument(
        "--filtrar-licitacoes",
        nargs="*",
        default=None,
        help="CSV(s) a extrair do ZIP do TCE-RS (ex.: licitacao.csv licitante.csv item.csv pessoas.csv)",
    )
    return parser.parse_args()


def _download_stream(url: str, *, timeout: int = 120) -> requests.Response:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Referer": "https://portaldatransparencia.gov.br/download-de-dados",
    }
    response = requests.get(url, timeout=timeout, allow_redirects=True, headers=headers)
    response.raise_for_status()
    return response


def _salvar_binario(response: requests.Response, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "wb") as handle:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                handle.write(chunk)
    return destino


def _descompactar_zip(caminho_zip: Path, destino: Path, nomes: list[str] | None = None) -> list[Path]:
    destino.mkdir(parents=True, exist_ok=True)
    com_filtro = [nome.lower() for nome in (nomes or [])]

    with zipfile.ZipFile(caminho_zip, "r") as pacote:
        membros = pacote.namelist()
        if com_filtro:
            membros = [m for m in membros if Path(m).name.lower() in com_filtro]

        if not membros:
            raise ValueError(f"Nenhum arquivo encontrado no ZIP para filtrar: {nomes}")

        pacote.extractall(destino, members=membros)
        arquivos_extraidos = [destino / nome for nome in membros]

    return arquivos_extraidos


def baixar_licitacoes_tce(ano: int, saida: Path, listar: bool = False, nomes: list[str] | None = None) -> list[str]:
    """Baixa o consolidado anual do TCE-RS (LicitaCon) e extrai o ZIP em data/raw/."""
    query = f"licitacoes consolidado {ano}"
    response = _download_stream(f"{CKAN_URL}?q={requests.utils.quote(query)}&rows=5")
    payload = response.json()
    if not payload.get("success", False):
        raise RuntimeError("Falha ao consultar a API CKAN do TCE-RS")

    datasets = payload["result"].get("results", [])
    urls = []
    for dataset in datasets:
        for resource in dataset.get("resources", []):
            url = resource.get("url")
            if url and url.endswith(".csv.zip") and f"/ano/{ano}.csv.zip" in url:
                urls.append(url)

    if not urls:
        raise RuntimeError(f"Nenhum recurso CSV ZIP encontrado para o ano {ano} no TCE-RS")

    if listar:
        for url in urls:
            print(url)
        return urls

    for url in urls:
        nome = Path(url).name
        destino_zip = saida / nome
        log.info("Baixando %s -> %s", url, destino_zip)
        response_zip = _download_stream(url)
        _salvar_binario(response_zip, destino_zip)
        extraidos = _descompactar_zip(destino_zip, saida, nomes=nomes)
        log.info("Extraído: %s arquivos para %s", len(extraidos), saida)

    return urls


def _resolver_data_ref(tipo: str, data_ref: str | None) -> str:
    """Escolhe a data disponível mais recente no portal de downloads."""
    if data_ref is not None:
        return data_ref

    base_url = PORTAL_CEIS_URL if tipo.upper() == "CEIS" else PORTAL_CNEP_URL
    response = _download_stream(base_url)
    html = response.text
    datas = sorted(set(re.findall(rf"{re.escape(base_url)}/(\d{{8}})", html)))
    if datas:
        return datas[-1]
    return FALLBACK_PORTAL_DATA


def baixar_sancoes_portal_transparencia(tipo: str, data_ref: str | None, saida: Path, listar: bool = False) -> list[str]:
    """Baixa CEIS ou CNEP do Portal da Transparência e extrai o ZIP."""
    base_url = PORTAL_CEIS_URL if tipo.upper() == "CEIS" else PORTAL_CNEP_URL
    data_ref = _resolver_data_ref(tipo, data_ref)
    url = f"{base_url}/{data_ref}"
    response = _download_stream(url)
    destino_final = response.url
    if listar:
        print(destino_final)
        return [destino_final]

    nome_zip = Path(destino_final).name
    destino_zip = saida / nome_zip
    log.info("Baixando %s -> %s", destino_final, destino_zip)
    response_zip = _download_stream(destino_final)
    _salvar_binario(response_zip, destino_zip)
    extraidos = _descompactar_zip(destino_zip, saida)
    log.info("Extraído: %s arquivos para %s", len(extraidos), saida)
    return [destino_final]


def baixar_cfil(url: str | None, saida: Path, listar: bool = False) -> list[str]:
    """Usa o arquivo CFIL/RS local já presente ou baixa pela URL informada."""
    origem = Path(url).expanduser() if url else config.CSV_CFIL

    if origem.exists():
        destino = saida / origem.name
        if not destino.exists() or destino.resolve() != origem.resolve():
            shutil.copy2(origem, destino)
        if listar:
            print(str(destino))
            return [str(destino)]
        log.info("Usando CFIL local em %s", destino)
        return [str(origem)]

    if not url:
        log.warning("Nenhum arquivo local de CFIL encontrado em %s; pulando download.", config.CSV_CFIL)
        return []

    response = _download_stream(url)
    if listar:
        print(response.url)
        return [response.url]

    destino = saida / Path(response.url).name
    log.info("Baixando CFIL -> %s", destino)
    _salvar_binario(response, destino)
    return [response.url]


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    saida = args.saida.resolve()
    saida.mkdir(parents=True, exist_ok=True)

    urls = []
    urls.extend(baixar_licitacoes_tce(args.ano, saida, listar=args.listar, nomes=args.filtrar_licitacoes))
    urls.extend(baixar_sancoes_portal_transparencia("CEIS", args.data_ceis, saida, listar=args.listar))
    urls.extend(baixar_sancoes_portal_transparencia("CNEP", args.data_cnep, saida, listar=args.listar))
    urls.extend(baixar_cfil(args.cfil_url, saida, listar=args.listar))

    if not args.listar:
        log.info("Download concluído. Arquivos em %s", saida)
        log.info("URLs processadas: %s", len(urls))


if __name__ == "__main__":
    main()
