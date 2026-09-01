from __future__ import annotations

import hashlib
import math
import re


class HashEmbeddingProvider:
    """Credential-free deterministic embedding for development and tests."""

    dimensions = 384

    def embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"\w+", text.casefold(), flags=re.UNICODE)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for offset in range(0, 8, 2):
                index = int.from_bytes(digest[offset : offset + 2]) % self.dimensions
                sign = 1.0 if digest[offset + 8] & 1 else -1.0
                vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]
