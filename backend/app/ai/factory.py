"""Build the configured Reader and Marker. Swapping models is a configuration change only."""

from app.ai.mock import MockMarker, MockReader
from app.ai.ollama import OllamaMarker, OllamaReader, resolve_model
from app.ai.ollama_client import OllamaClient
from app.ai.types import Marker, Reader
from app.config import Settings


def ollama_client(settings: Settings) -> OllamaClient:
    return OllamaClient(
        settings.model_base_url,
        settings.model_timeout_seconds,
        think=settings.model_think,
        max_output_tokens=settings.model_max_output_tokens,
        context_tokens=settings.model_context_tokens,
    )


def build_reader(settings: Settings) -> Reader:
    if settings.ai_backend == "mock":
        return MockReader(settings.mock_delay_seconds)
    client = ollama_client(settings)
    return OllamaReader(
        client,
        resolve_model(client, settings.reader_model),
        max_image_px=settings.reader_max_image_px,
        output_retries=settings.model_output_retries,
    )


def build_marker(settings: Settings) -> Marker:
    if settings.ai_backend == "mock":
        return MockMarker(settings.mock_delay_seconds, evidence=settings.marker_evidence)
    client = ollama_client(settings)
    return OllamaMarker(
        client,
        resolve_model(client, settings.marker_model),
        output_retries=settings.model_output_retries,
        evidence=settings.marker_evidence,
    )
