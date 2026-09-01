from __future__ import annotations

from typing import Any


class MultilingualE5Provider:
    dimensions = 384

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small") -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError(
                "Install the 'embeddings' extra to use multilingual-e5-small"
            ) from error
        self.model: Any = SentenceTransformer(model_name)

    def embed_one(self, text: str) -> list[float]:
        result = self.model.encode(
            f"query: {text}", normalize_embeddings=True, convert_to_numpy=True
        )
        return [float(value) for value in result.tolist()]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        prefixed = [f"passage: {text}" for text in texts]
        results = self.model.encode(
            prefixed, normalize_embeddings=True, convert_to_numpy=True
        )
        return [[float(value) for value in row.tolist()] for row in results]
