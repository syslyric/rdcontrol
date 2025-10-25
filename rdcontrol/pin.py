"""PIN management for rdcontrol."""
from __future__ import annotations

import json
import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .config import ControlConfig

_PIN_LENGTH = 6
_CHILD_PIN_LIFETIME = timedelta(seconds=15)


@dataclass
class StoredPins:
    """Dataclass describing stored PIN data."""

    parent_hash: str
    child_pin: Optional[str] = None
    child_pin_expires_at: Optional[str] = None
    child_access_until: Optional[str] = None
    pending_allowance_minutes: Optional[int] = None

    def to_payload(self) -> dict:
        return {
            "parent_hash": self.parent_hash,
            "child_pin": self.child_pin,
            "child_pin_expires_at": self.child_pin_expires_at,
            "child_access_until": self.child_access_until,
            "pending_allowance_minutes": self.pending_allowance_minutes,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "StoredPins":
        return cls(
            parent_hash=payload["parent_hash"],
            child_pin=payload.get("child_pin"),
            child_pin_expires_at=payload.get("child_pin_expires_at"),
            child_access_until=payload.get("child_access_until"),
            pending_allowance_minutes=payload.get("pending_allowance_minutes"),
        )


class PinStorage:
    """Persist PIN metadata to disk."""

    def __init__(self, path: Path):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Optional[StoredPins]:
        if not self._path.exists():
            return None
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return StoredPins.from_payload(payload)

    def save(self, pins: StoredPins) -> None:
        self._path.write_text(
            json.dumps(pins.to_payload(), indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _hash_pin(pin: str) -> str:
    import hashlib

    salt = b"rdcontrol-salt"
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 390000)
    return digest.hex()


class PinManager:
    """Manage parent/child PIN lifecycles."""

    def __init__(self, config: ControlConfig):
        self._config = config
        self._storage = PinStorage(config.pin_store)
        stored = self._storage.load()
        if stored:
            self._pins = stored
        else:
            raise RuntimeError(
                "Pin store missing. Run `rdcontrol init --parent-pin <pin>` first."
            )

    @classmethod
    def initialize(cls, config: ControlConfig, parent_pin: str) -> None:
        storage = PinStorage(config.pin_store)
        if storage.load() is not None:
            raise ValueError("PIN store already initialised")
        storage.save(StoredPins(parent_hash=_hash_pin(parent_pin)))

    def verify_parent_pin(self, pin: str) -> bool:
        return secrets.compare_digest(self._pins.parent_hash, _hash_pin(pin))

    def generate_child_pin(self, allowance_minutes: int | None = None) -> str:
        if allowance_minutes is None:
            allowance_minutes = self._config.child_time_allowance_minutes
        if allowance_minutes <= 0:
            raise ValueError("Allowance minutes must be greater than zero")
        alphabet = string.digits
        pin = "".join(secrets.choice(alphabet) for _ in range(_PIN_LENGTH))
        expires = datetime.now(timezone.utc) + _CHILD_PIN_LIFETIME
        self._pins.child_pin = pin
        self._pins.child_pin_expires_at = expires.isoformat()
        self._pins.pending_allowance_minutes = int(allowance_minutes)
        self._storage.save(self._pins)
        return pin

    def verify_child_pin(self, pin: str) -> bool:
        if not self._pins.child_pin or not self._pins.child_pin_expires_at:
            return False
        expires = datetime.fromisoformat(self._pins.child_pin_expires_at)
        if datetime.now(timezone.utc) > expires:
            return False
        if not secrets.compare_digest(self._pins.child_pin, pin):
            return False
        return True

    def consume_child_pin(
        self, pin: str, duration_minutes: int | None = None
    ) -> Optional[datetime]:
        if not self.verify_child_pin(pin):
            return None
        if duration_minutes is None:
            duration_minutes = (
                self._pins.pending_allowance_minutes
                or self._config.child_time_allowance_minutes
            )
        if duration_minutes <= 0:
            return None
        allow_until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        self._pins.child_pin = None
        self._pins.child_pin_expires_at = None
        self._pins.child_access_until = allow_until.isoformat()
        self._pins.pending_allowance_minutes = None
        self._storage.save(self._pins)
        return allow_until

    def child_time_remaining(self) -> timedelta:
        if not self._pins.child_access_until:
            return timedelta(0)
        expires = datetime.fromisoformat(self._pins.child_access_until)
        remaining = expires - datetime.now(timezone.utc)
        return max(remaining, timedelta(0))

    def revoke_child_access(self) -> None:
        self._pins.child_pin = None
        self._pins.child_pin_expires_at = None
        self._pins.child_access_until = None
        self._pins.pending_allowance_minutes = None
        self._storage.save(self._pins)

    def parent_override(self) -> None:
        allow_until = datetime.now(timezone.utc) + timedelta(days=365 * 10)
        self._pins.child_pin = None
        self._pins.child_pin_expires_at = None
        self._pins.child_access_until = allow_until.isoformat()
        self._pins.pending_allowance_minutes = None
        self._storage.save(self._pins)
