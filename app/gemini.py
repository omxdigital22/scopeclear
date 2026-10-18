"""Thin Gemini wrapper.

On Cloud Run it uses Vertex AI with the service account, so no API key exists
anywhere. Locally you may set GEMINI_API_KEY in a .env file that is gitignored.
MOCK_GEMINI=1 skips Gemini entirely (UI development only, never for judging).
"""
import os
import time
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MOCK = os.getenv("MOCK_GEMINI") == "1"

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        if os.getenv("GEMINI_API_KEY"):
            _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        else:
            _client = genai.Client(
                vertexai=True,
                project=os.getenv("GOOGLE_CLOUD_PROJECT"),
                location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
    return _client


def part_bytes(data: bytes, mime: str):
    from google.genai import types
    return types.Part.from_bytes(data=data, mime_type=mime)


def generate(contents: list, schema: Type[T], system: str, temperature: float = 0.1) -> T:
    """Call Gemini with a strict JSON schema. Retries twice on failure."""
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_schema=schema,
        temperature=temperature,
    )
    last_err = None
    for attempt in range(3):
        try:
            resp = _get_client().models.generate_content(model=MODEL, contents=contents, config=config)
            if isinstance(resp.parsed, schema):
                return resp.parsed
            return schema.model_validate_json(resp.text)
        except Exception as e:  # network, quota, malformed JSON
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Gemini call failed after 3 attempts: {last_err}")
