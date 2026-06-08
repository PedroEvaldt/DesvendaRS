"""Gemini-powered textual overview for a licitation dossier.

The model is used only as an assistive layer. It must summarize evidence and
surface hypotheses for human review, never assert that fraud happened.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx


DEFAULT_MODEL = "gemini-1.5-flash"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


@dataclass(frozen=True)
class AIOverview:
    """Normalized result shown by the web UI."""

    enabled: bool
    status: str
    title: str
    summary: str
    bullets: list[str]
    limitations: list[str]
    raw_text: str | None = None


def api_key_from_env() -> str | None:
    """Return Gemini API key from environment variables.

    Supports both names because teams commonly use either one locally.
    """
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def generate_licitacao_overview(
    context: dict[str, Any],
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float = 18.0,
) -> AIOverview:
    """Ask Gemini for a concise, structured overview of one licitation."""
    key = api_key or api_key_from_env()
    if not key:
        return AIOverview(
            enabled=False,
            status="missing_key",
            title="IA não configurada",
            summary=(
                "Configure GEMINI_API_KEY ou GOOGLE_API_KEY no ambiente para gerar "
                "o overview textual desta licitação."
            ),
            bullets=[],
            limitations=[],
        )

    prompt = _build_prompt(context)
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
            "maxOutputTokens": 1200,
        },
    }
    url = GEMINI_ENDPOINT.format(model=model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL))

    try:
        response = httpx.post(
            url,
            params={"key": key},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        text = _extract_text(response.json())
    except httpx.HTTPError as exc:
        return AIOverview(
            enabled=True,
            status="error",
            title="Overview da IA indisponível",
            summary=f"Não foi possível consultar o Gemini agora: {exc}",
            bullets=[],
            limitations=["A análise automática não foi gerada nesta abertura do dossiê."],
        )
    except (KeyError, TypeError, ValueError) as exc:
        return AIOverview(
            enabled=True,
            status="error",
            title="Resposta da IA não reconhecida",
            summary=f"O Gemini respondeu em um formato inesperado: {exc}",
            bullets=[],
            limitations=["A análise textual precisa ser refeita."],
        )

    parsed = _parse_json_object(text)
    if not parsed:
        return AIOverview(
            enabled=True,
            status="ok",
            title="Overview da IA",
            summary=text.strip(),
            bullets=[],
            limitations=["Resposta sem estrutura JSON; leia como comentário auxiliar."],
            raw_text=text,
        )

    return AIOverview(
        enabled=True,
        status="ok",
        title=str(parsed.get("titulo") or "Overview da IA"),
        summary=str(parsed.get("resumo") or "").strip(),
        bullets=_string_list(parsed.get("pontos_de_atencao")),
        limitations=_string_list(parsed.get("limitacoes")),
        raw_text=text,
    )


def _build_prompt(context: dict[str, Any]) -> str:
    data = json.dumps(context, ensure_ascii=False, default=str, indent=2)
    return f"""
Você é um analista de apoio do projeto DesvendaRS. Avalie uma licitação usando
somente os dados fornecidos abaixo.

Regras obrigatórias:
- Escreva em português do Brasil.
- Não afirme fraude, culpa, dolo ou irregularidade comprovada.
- Use linguagem de indício: "merece revisão", "pode indicar", "não há evidência suficiente".
- Se faltar justificativa/fundamento textual, diga claramente que a fonte carregada não permite concluir.
- Avalie compatibilidade entre objeto, empresa vencedora, CNAE, capital social, sanções, concorrentes, valores e red flags automáticas.
- Se a modalidade for dispensa ou inexigibilidade, avalie se os dados textuais disponíveis tornam a justificativa plausível; se não houver justificativa, trate como limitação.
- Não invente lei, artigo, documento externo, endereço ou dado que não esteja no JSON.

Responda somente um JSON válido neste formato:
{{
  "titulo": "frase curta",
  "resumo": "parágrafo de 3 a 5 frases com a avaliação geral",
  "pontos_de_atencao": [
    "até 5 pontos objetivos, cada um com evidência do JSON"
  ],
  "limitacoes": [
    "dados ausentes ou ressalvas importantes"
  ]
}}

Dados da licitação:
{data}
""".strip()


def _extract_text(payload: dict[str, Any]) -> str:
    candidates = payload["candidates"]
    parts = candidates[0]["content"]["parts"]
    return "\n".join(str(part.get("text", "")) for part in parts).strip()


def _parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result
