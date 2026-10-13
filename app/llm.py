"""Small OpenRouter client shared by the specialist agents."""
import base64
import json
import re
from typing import Optional

import httpx

from .config import settings


class LLM:
    """Send chat and vision requests through OpenRouter's chat completions API."""

    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    @property
    def live(self) -> bool:
        return bool(settings.openrouter_api_key)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": settings.openrouter_title,
            "X-OpenRouter-App-Visibility": settings.openrouter_visibility,
        }
        if settings.openrouter_referer:
            headers["HTTP-Referer"] = settings.openrouter_referer
        return headers

    def _request(self, messages: list[dict], max_tokens: int) -> str:
        response = httpx.post(
            self.endpoint,
            headers=self._headers(),
            json={"model": settings.model, "messages": messages, "max_tokens": max_tokens},
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"].get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                part.get("text", "") for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        return ""

    def complete(self, system: str, user: str, max_tokens: int = 4096) -> str:
        return self._request(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens,
        )

    def json(self, system: str, user: str, max_tokens: int = 8000) -> Optional[dict]:
        """Ask for JSON only. Returns None offline or if the reply can't be parsed."""
        if not self.live:
            return None
        try:
            text = self.complete(
                system + "\nReply with a single JSON object and nothing else.", user, max_tokens
            )
            match = re.search(r"\{.*\}", text, re.S)
            value = json.loads(match.group(0)) if match else None
            return value if isinstance(value, dict) else None
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            return None

    def describe_image(self, data: bytes, media_type: str) -> str:
        """Ask a vision-capable OpenRouter model to transcribe and describe an image."""
        if not self.live:
            return ""
        encoded = base64.b64encode(data).decode("ascii")
        try:
            return self._request(
                [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:{media_type};base64,{encoded}"
                    }},
                    {"type": "text", "text": "Transcribe all text in this image faithfully, preserving "
                     "headings, lists and tables as markdown, then describe its layout and style."},
                ]}],
                2000,
            )
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            return ""


llm = LLM()
