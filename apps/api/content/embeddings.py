"""
MediaCompile — Embedding Service.

Provides a provider-neutral embedding interface supporting:
- LocalEmbeddingProvider: runs sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)
  on CPU via ONNX Runtime and HuggingFace Tokenizers with L2 unit normalization.
- MockEmbeddingProvider: generates deterministic 384-dimensional unit vectors from
  token hashes for offline testing and fallback environments.
"""

import hashlib
import logging
import math
import os
from pathlib import Path
from typing import List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_DIMENSION = 384
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""


class EmbeddingDimensionMismatchError(EmbeddingError):
    """Raised when generated embedding dimension doesn't match expected dimension."""


class BaseEmbeddingProvider:
    """Abstract base class for embedding providers."""

    def __init__(self, model_name: str = DEFAULT_MODEL, dimension: int = DEFAULT_DIMENSION):
        self.model_name = model_name
        self.dimension = dimension

    def embed_text(self, text: str) -> List[float]:
        raise NotImplementedError

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """
    Deterministic mock embedding provider.
    Generates repeatable, unit-normalized 384-dimensional vectors based on token hashes.
    """

    def embed_text(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self.dimension

        vector = [0.0] * self.dimension
        words = text.lower().split()

        for idx, word in enumerate(words):
            h = int(hashlib.sha256(word.encode('utf-8')).hexdigest(), 16)
            dim_index = h % self.dimension
            vector[dim_index] += 1.0 / math.sqrt(idx + 1)

        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [round(v / norm, 6) for v in vector]
        else:
            vector[0] = 1.0

        if len(vector) != self.dimension:
            raise EmbeddingDimensionMismatchError(
                f"Generated dimension {len(vector)} does not match expected {self.dimension}"
            )
        return vector

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]


class LocalEmbeddingProvider(BaseEmbeddingProvider):
    """
    Local embedding provider executing sentence-transformers/all-MiniLM-L6-v2 (384 dimensions)
    via ONNX Runtime and HuggingFace Tokenizers on CPU.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, dimension: int = DEFAULT_DIMENSION):
        super().__init__(model_name=model_name, dimension=dimension)
        self._session = None
        self._tokenizer = None
        self._fallback_provider = MockEmbeddingProvider(model_name=model_name, dimension=dimension)
        self._initialize_model()

    def _get_model_paths(self) -> tuple[Optional[Path], Optional[Path]]:
        """Locate local ONNX model and tokenizer files across standard cache directories."""
        base_dir = getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent)
        candidates = [
            Path(base_dir) / 'models' / 'all-MiniLM-L6-v2',
            Path(os.environ.get('USERPROFILE', '.')) / '.cache' / 'mediacompile_embeddings' / 'all-MiniLM-L6-v2',
            Path(base_dir) / '.cache' / 'embeddings' / 'all-MiniLM-L6-v2',
        ]
        for c in candidates:
            tok = c / 'tokenizer.json'
            mod = c / 'model_quantized.onnx'
            if not mod.exists():
                mod = c / 'model.onnx'
            if tok.exists() and mod.exists():
                return tok, mod

        for c in candidates:
            tok = c / 'tokenizer.json'
            if tok.exists():
                return tok, None

        return None, None

    def _initialize_model(self) -> None:
        """Initialize the ONNX Runtime session and tokenizer once."""
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer

            tok_path, model_path = self._get_model_paths()

            if tok_path and model_path and tok_path.exists() and model_path.exists():
                self._tokenizer = Tokenizer.from_file(str(tok_path))
                self._tokenizer.enable_truncation(max_length=512)
                self._tokenizer.enable_padding(pad_id=0, pad_token='[PAD]')

                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 2
                self._session = ort.InferenceSession(str(model_path), sess_options=opts, providers=['CPUExecutionProvider'])
                logger.info("Loaded local ONNX embedding model: %s", self.model_name)
            else:
                logger.info(
                    "Local ONNX model files not found at expected paths; using deterministic 384-dim unit vector provider."
                )
        except Exception as e:
            logger.warning("Local embedding model initialization failed (%s); using fallback.", e)
            self._session = None
            self._tokenizer = None

    def embed_text(self, text: str) -> List[float]:
        results = self.embed_batch([text])
        return results[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        if self._session is not None and self._tokenizer is not None:
            try:
                import numpy as np

                clean_texts = [t.strip() if t and t.strip() else " " for t in texts]
                encoded_batch = self._tokenizer.encode_batch(clean_texts)

                input_ids = np.array([e.ids for e in encoded_batch], dtype=np.int64)
                attention_mask = np.array([e.attention_mask for e in encoded_batch], dtype=np.int64)
                token_type_ids = np.array([e.type_ids for e in encoded_batch], dtype=np.int64)

                outputs = self._session.run(None, {
                    'input_ids': input_ids,
                    'attention_mask': attention_mask,
                    'token_type_ids': token_type_ids
                })

                last_hidden_state = outputs[0]

                # Mean pooling over non-masked tokens followed by L2 unit normalization
                mask_expanded = np.expand_dims(attention_mask, -1).astype(float)
                sum_embeddings = np.sum(last_hidden_state * mask_expanded, axis=1)
                sum_mask = np.clip(mask_expanded.sum(axis=1), a_min=1e-9, a_max=None)
                mean_pooled = sum_embeddings / sum_mask

                norms = np.linalg.norm(mean_pooled, axis=1, keepdims=True)
                norms = np.clip(norms, a_min=1e-9, a_max=None)
                normalized = (mean_pooled / norms).tolist()

                for vec in normalized:
                    if len(vec) != self.dimension:
                        raise EmbeddingDimensionMismatchError(
                            f"Model produced vector with dimension {len(vec)}, expected {self.dimension}"
                        )
                return normalized
            except Exception as e:
                logger.error("ONNX inference failed (%s); falling back to deterministic vector provider.", e)

        return self._fallback_provider.embed_batch(texts)


_CACHED_PROVIDER: Optional[BaseEmbeddingProvider] = None


def get_embedding_provider() -> BaseEmbeddingProvider:
    """
    Return the configured singleton embedding provider ('local' or 'mock').
    """
    global _CACHED_PROVIDER

    provider_type = "local"
    model_name = DEFAULT_MODEL
    dimension = DEFAULT_DIMENSION

    if settings.configured:
        provider_type = getattr(
            settings, "EMBEDDING_PROVIDER", os.environ.get("EMBEDDING_PROVIDER", "local")
        ).lower()
        model_name = getattr(
            settings, "EMBEDDING_MODEL", os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL)
        )
        if model_name == "text-embedding-3-small" or "all-minilm-l6-v2" in model_name.lower():
            model_name = DEFAULT_MODEL
            dimension = DEFAULT_DIMENSION
        else:
            dimension = int(
                getattr(
                    settings,
                    "EMBEDDING_DIMENSIONS",
                    getattr(
                        settings,
                        "EMBEDDING_DIMENSION",
                        os.environ.get("EMBEDDING_DIMENSIONS", os.environ.get("EMBEDDING_DIMENSION", str(DEFAULT_DIMENSION)))
                    )
                )
            )
            if dimension == 1536:
                model_name = DEFAULT_MODEL
                dimension = DEFAULT_DIMENSION
    else:
        provider_type = os.environ.get("EMBEDDING_PROVIDER", "local").lower()
        model_name = os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL)
        if model_name == "text-embedding-3-small" or "all-minilm-l6-v2" in model_name.lower():
            model_name = DEFAULT_MODEL
            dimension = DEFAULT_DIMENSION
        else:
            dimension = int(os.environ.get("EMBEDDING_DIMENSIONS", os.environ.get("EMBEDDING_DIMENSION", str(DEFAULT_DIMENSION))))
            if dimension == 1536:
                model_name = DEFAULT_MODEL
                dimension = DEFAULT_DIMENSION

    if (
        _CACHED_PROVIDER is not None and
        getattr(_CACHED_PROVIDER, 'dimension', None) == dimension and
        getattr(_CACHED_PROVIDER, 'model_name', None) == model_name
    ):
        return _CACHED_PROVIDER

    if provider_type in ("local", "huggingface", "transformers"):
        _CACHED_PROVIDER = LocalEmbeddingProvider(
            model_name=model_name,
            dimension=dimension
        )
    else:
        _CACHED_PROVIDER = MockEmbeddingProvider(
            model_name=model_name,
            dimension=dimension
        )

    return _CACHED_PROVIDER
