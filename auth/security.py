from __future__ import annotations

from dataclasses import dataclass

try:  # pragma: no cover - import guard for environments without argon2
    from argon2 import PasswordHasher  # type: ignore
    from argon2.exceptions import VerifyMismatchError  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    PasswordHasher = None  # type: ignore[assignment]

    class VerifyMismatchError(Exception):
        ...


@dataclass(slots=True)
class PasswordHashingError(Exception):
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class Argon2PasswordHasher:
    """Argon2id-based password hasher."""

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        if PasswordHasher is None and hasher is None:  # pragma: no cover - guard
            raise RuntimeError("argon2-cffi is required but not installed")
        self._hasher = hasher or PasswordHasher()

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, hashed_password: str, candidate: str) -> bool:
        try:
            return self._hasher.verify(hashed_password, candidate)
        except VerifyMismatchError:
            return False


__all__ = ["Argon2PasswordHasher", "PasswordHashingError"]
