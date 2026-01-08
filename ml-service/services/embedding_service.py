"""
Embedding Service for Semantic Search

Uses sentence-transformers to generate embeddings for session notes.
Embeddings are stored in PostgreSQL with pgvector for similarity search.
"""

import os
import logging
from typing import List, Optional, Union
import numpy as np

logger = logging.getLogger(__name__)

# Lazy load to avoid import errors if torch not available
_model = None
_model_name = None


def _get_model():
    """Lazy load the embedding model."""
    global _model, _model_name

    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            model_name = os.getenv('EMBEDDING_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2')
            cache_dir = os.getenv('EMBEDDING_CACHE_DIR', None)

            logger.info(f"Loading embedding model: {model_name}")

            _model = SentenceTransformer(model_name, cache_folder=cache_dir)
            _model_name = model_name

            logger.info(f"Embedding model loaded successfully: {model_name}")
            logger.info(f"Embedding dimensions: {_model.get_sentence_embedding_dimension()}")

        except ImportError as e:
            logger.error(f"Failed to import sentence-transformers: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise

    return _model


class EmbeddingService:
    """
    Service for generating text embeddings using sentence-transformers.

    Uses paraphrase-multilingual-MiniLM-L12-v2 by default which supports
    50+ languages including Czech and produces 384-dimensional embeddings.
    """

    def __init__(self):
        self._model = None

    @property
    def model(self):
        """Lazy load model on first access."""
        if self._model is None:
            self._model = _get_model()
        return self._model

    @property
    def dimensions(self) -> int:
        """Get embedding dimensions."""
        return self.model.get_sentence_embedding_dimension()

    @property
    def model_name(self) -> str:
        """Get model name."""
        return _model_name or os.getenv('EMBEDDING_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2')

    def embed(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding, or None if text is empty
        """
        if not text or not text.strip():
            return None

        try:
            embedding = self.model.encode(text, convert_to_numpy=True)

            # Normalize for cosine similarity
            embedding = embedding / np.linalg.norm(embedding)

            return embedding.tolist()

        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

    def embed_batch(self, texts: List[str], batch_size: int = 32) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of input texts
            batch_size: Batch size for encoding

        Returns:
            List of embeddings (or None for empty texts)
        """
        results = []
        valid_texts = []
        valid_indices = []

        # Filter valid texts
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
                valid_indices.append(i)

        if valid_texts:
            try:
                embeddings = self.model.encode(
                    valid_texts,
                    batch_size=batch_size,
                    convert_to_numpy=True,
                    normalize_embeddings=True  # Normalize for cosine similarity
                )

                # Map embeddings back to original positions
                embedding_map = {
                    valid_indices[i]: embeddings[i].tolist()
                    for i in range(len(valid_indices))
                }

                for i in range(len(texts)):
                    results.append(embedding_map.get(i))

            except Exception as e:
                logger.error(f"Error generating batch embeddings: {e}")
                results = [None] * len(texts)
        else:
            results = [None] * len(texts)

        return results

    def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding
            embedding2: Second embedding

        Returns:
            Cosine similarity score (0-1)
        """
        try:
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)

            # Cosine similarity
            similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

            return float(similarity)

        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            return 0.0

    def health_check(self) -> dict:
        """
        Check if embedding service is healthy.

        Returns:
            Dict with status and model info
        """
        try:
            # Try to load model
            model = self.model

            # Test embedding
            test_embedding = self.embed("test")

            return {
                'status': 'healthy',
                'model': self.model_name,
                'dimensions': self.dimensions,
                'test_embedding_length': len(test_embedding) if test_embedding else 0
            }

        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }


# Singleton instance
embedding_service = EmbeddingService()


# Convenience functions
def embed_text(text: str) -> Optional[List[float]]:
    """Generate embedding for text."""
    return embedding_service.embed(text)


def embed_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """Generate embeddings for multiple texts."""
    return embedding_service.embed_batch(texts)
