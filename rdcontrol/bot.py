"""Telegram bot integration for rdcontrol."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from telegram import Update
from telegram.ext import (Application, ApplicationBuilder, CommandHandler,
                          ContextTypes)

from .config import ControlConfig
from .pin import PinManager

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    token: str
    allowed_chat_ids: Iterable[int]


class ControlBot:
    """Telegram bot that exposes remote management commands."""

    def __init__(self, config: ControlConfig, pin_manager: PinManager):
        if not config.telegram_bot_token:
            raise ValueError("Telegram bot token missing from configuration")
        self._pin_manager = pin_manager
        self._bot_config = BotConfig(
            token=config.telegram_bot_token,
            allowed_chat_ids=tuple(config.telegram_parent_chat_ids),
        )
        self._app: Application | None = None

    async def _authorize(self, update: Update) -> bool:
        if not self._bot_config.allowed_chat_ids:
            return True
        chat_id = update.effective_chat.id if update.effective_chat else None
        authorized = chat_id in self._bot_config.allowed_chat_ids
        if not authorized:
            logger.warning("Unauthorized chat %s attempted to use bot", chat_id)
            if update.message:
                await update.message.reply_text("Access denied")
        return authorized

    async def _handle_generate_child_pin(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._authorize(update):
            return
        try:
            pin = self._pin_manager.generate_child_pin()
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        await update.message.reply_text(
            "Child PIN: {pin} (expires in 15s). Use the CLI `claim` command to activate."
            .format(pin=pin)
        )

    async def _handle_grant_time(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._authorize(update):
            return
        try:
            minutes = int(context.args[0])
        except (IndexError, ValueError):
            await update.message.reply_text("Usage: /grant <minutes>")
            return
        try:
            pin = self._pin_manager.generate_child_pin(minutes)
        except ValueError as exc:
            await update.message.reply_text(str(exc))
            return
        await update.message.reply_text(
            f"Generated PIN {pin}. Share it with the child within 15 seconds. "
            "They must run `python -m rdcontrol claim {pin}` to start the timer."
        )

    async def _handle_revoke(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._authorize(update):
            return
        self._pin_manager.revoke_child_access()
        await update.message.reply_text("Child access revoked")

    async def _handle_status(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._authorize(update):
            return
        remaining = self._pin_manager.child_time_remaining()
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        await update.message.reply_text(
            f"Child time remaining: {minutes}m {seconds}s"
        )

    async def _handle_parent_override(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not await self._authorize(update):
            return
        self._pin_manager.parent_override()
        await update.message.reply_text("Parent override activated")

    async def start(self) -> None:
        if self._app:
            raise RuntimeError("Bot already running")
        builder = ApplicationBuilder().token(self._bot_config.token)
        self._app = builder.build()
        self._app.add_handler(CommandHandler("pin", self._handle_generate_child_pin))
        self._app.add_handler(CommandHandler("grant", self._handle_grant_time))
        self._app.add_handler(CommandHandler("revoke", self._handle_revoke))
        self._app.add_handler(CommandHandler("status", self._handle_status))
        self._app.add_handler(CommandHandler("override", self._handle_parent_override))
        logger.info("Starting Telegram bot")
        await self._app.initialize()
        await self._app.start()
        if self._app.updater:
            await self._app.updater.start_polling()

    async def close(self) -> None:
        if not self._app:
            return
        logger.info("Stopping Telegram bot")
        if self._app.updater:
            await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        self._app = None
