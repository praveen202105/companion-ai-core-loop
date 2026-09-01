from typing import Protocol


class EmbeddingProvider(Protocol):
    dimensions: int

    def embed_one(self, text: str) -> list[float]: ...

    def embed_many(self, texts: list[str]) -> list[list[float]]: ...
