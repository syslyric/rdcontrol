"""Configuration helpers for rdcontrol."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence

import yaml


@dataclass
class ControlConfig:
    """Configuration model describing parental-control behaviour."""

    blocklist: Sequence[str] = field(default_factory=tuple)
    pin_store: Path = Path("~/.config/rdcontrol/pins.json").expanduser()
    child_time_allowance_minutes: int = 0
    telegram_bot_token: str | None = None
    telegram_parent_chat_ids: Sequence[int] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if isinstance(self.pin_store, str):
            self.pin_store = Path(self.pin_store).expanduser()
        else:
            self.pin_store = Path(self.pin_store).expanduser()
        self.blocklist = tuple(self.blocklist or [])
        if self.telegram_parent_chat_ids is None:
            self.telegram_parent_chat_ids = tuple()
        else:
            self.telegram_parent_chat_ids = tuple(int(cid) for cid in self.telegram_parent_chat_ids)
        self.child_time_allowance_minutes = int(self.child_time_allowance_minutes)

    @property
    def normalized_blocklist(self) -> List[str]:
        """Return process names in lowercase for comparison."""
        return [proc.lower() for proc in self.blocklist]


def load_config(path: Path | str) -> ControlConfig:
    """Load a configuration from a YAML file."""
    config_path = Path(path).expanduser()
    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    return ControlConfig(**payload)


def dump_default_config(path: Path | str) -> None:
    """Create a starter configuration file."""
    template = ControlConfig(
        blocklist=(
            "robloxplayerbeta.exe",
            "steam.exe",
            "fortniteclient-win64-shipping.exe",
        ),
        child_time_allowance_minutes=90,
    )
    Path(path).expanduser().write_text(
        yaml.safe_dump(
            {
                "blocklist": list(template.blocklist),
                "pin_store": str(template.pin_store),
                "child_time_allowance_minutes": template.child_time_allowance_minutes,
                "telegram_bot_token": template.telegram_bot_token,
                "telegram_parent_chat_ids": list(template.telegram_parent_chat_ids),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
