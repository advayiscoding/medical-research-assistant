"""Process-wide VectorStore singleton.

The Chroma PersistentClient holds a file lock / DB handle on its data dir;
creating one per request would contend and leak handles. One per process,
built lazily on first use, mirrors how we manage the SQLAlchemy engine.
"""

from app.core.config import get_settings
from app.services.vector_store import VectorStore

_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore(get_settings())
    return _store


def reset_vector_store() -> None:
    """Test hook — drop the singleton so a test can point at a fresh dir."""
    global _store
    _store = None
