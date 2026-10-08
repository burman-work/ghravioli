"""Injectable instance identity providers for archive construction."""

from __future__ import annotations

import uuid
from typing import Protocol


class IdentityProvider(Protocol):
    """Provide a new UUID string for every archive instance."""

    def new(self) -> str:
        """Return a unique UUID string."""


class UUID4IdentityProvider:
    """Generate random identities for production archives."""

    def new(self) -> str:
        return str(uuid.uuid4())


class SequenceIdentityProvider:
    """Generate reproducible identities for tests and explicitly controlled builds."""

    def __init__(self, namespace: uuid.UUID = uuid.NAMESPACE_URL) -> None:
        self._namespace = namespace
        self._index = 0

    def new(self) -> str:
        value = uuid.uuid5(self._namespace, f"ghravioli:{self._index}")
        self._index += 1
        return str(value)
