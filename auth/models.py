from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator
import re

if TYPE_CHECKING:
    from .session import SessionToken


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegistrationRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320, examples=["user@example.com"])
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid email format")
        return normalized


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("Invalid email format")
        return normalized


class SessionResponse(BaseModel):
    user_id: str
    expires_at: datetime


@dataclass(slots=True)
class User:
    id: str
    email: str
    password_hash: str
    created_at: datetime


@dataclass(slots=True)
class AuthenticatedSession:
    token: "SessionToken"
    user_id: str
    expires_at: datetime


__all__ = [
    "AuthenticatedSession",
    "LoginRequest",
    "RegistrationRequest",
    "SessionResponse",
    "User",
]
