"""Process monitoring utilities."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta

import psutil

from .config import ControlConfig
from .pin import PinManager

logger = logging.getLogger(__name__)


@dataclass
class MonitorStats:
    killed_processes: int = 0


class ProcessMonitor:
    """Monitor running processes and terminate forbidden ones."""

    def __init__(self, config: ControlConfig, pin_manager: PinManager):
        self.config = config
        self.pin_manager = pin_manager
        self.stats = MonitorStats()

    def _should_block(self) -> bool:
        remaining = self.pin_manager.child_time_remaining()
        return remaining <= timedelta(0)

    def scan_once(self) -> None:
        if not self._should_block():
            return
        blocklist = set(self.config.normalized_blocklist)
        for proc in psutil.process_iter(["name"]):
            name = (proc.info.get("name") or "").lower()
            if name and name in blocklist:
                try:
                    proc.terminate()
                    self.stats.killed_processes += 1
                    logger.info("Terminated blocked process %s", name)
                except psutil.Error as exc:
                    logger.warning("Failed to terminate %s: %s", name, exc)

    def run(self, interval_seconds: float = 5.0) -> None:
        logger.info("Starting process monitor with interval=%s", interval_seconds)
        try:
            while True:
                self.scan_once()
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            logger.info("Process monitor interrupted by user")
