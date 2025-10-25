"""Command line interface for rdcontrol."""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Callable

from .bot import ControlBot
from .config import ControlConfig, dump_default_config, load_config
from .monitor import ProcessMonitor
from .pin import PinManager

DEFAULT_CONFIG_PATH = Path("~/.config/rdcontrol/config.yaml").expanduser()


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _load_config(path: Path | str) -> ControlConfig:
    return load_config(Path(path).expanduser())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parental control toolkit")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to YAML configuration file (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Initialise the PIN store")
    init.add_argument("--parent-pin", required=True, help="Parent PIN to set")

    sub.add_parser("status", help="Show remaining child time")
    sub.add_parser("generate", help="Generate a short-lived child PIN")

    claim = sub.add_parser("claim", help="Claim child time using a PIN")
    claim.add_argument("pin", help="Child PIN value")
    claim.add_argument(
        "--minutes",
        type=int,
        default=None,
        help="Override allowance duration in minutes",
    )

    sub.add_parser("revoke", help="Revoke any granted child access")
    sub.add_parser("override", help="Give unlimited access until revoked")
    monitor = sub.add_parser("monitor", help="Start the process monitor loop")
    monitor.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Scan interval in seconds (default: 5.0)",
    )

    scaffold = sub.add_parser("scaffold-config", help="Create default config file")
    scaffold.add_argument(
        "--output",
        default=str(DEFAULT_CONFIG_PATH),
        help="Where to write the new configuration file",
    )

    sub.add_parser("run-bot", help="Start Telegram bot")

    return parser


def cmd_init(config: ControlConfig, args: argparse.Namespace) -> int:
    try:
        PinManager.initialize(config, args.parent_pin)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Stored parent PIN in {config.pin_store}")
    return 0


def cmd_status(config: ControlConfig, _: argparse.Namespace) -> int:
    manager = PinManager(config)
    remaining = manager.child_time_remaining()
    minutes = int(remaining.total_seconds() // 60)
    seconds = int(remaining.total_seconds() % 60)
    print(f"Child time remaining: {minutes}m {seconds}s")
    return 0


def cmd_generate(config: ControlConfig, _: argparse.Namespace) -> int:
    manager = PinManager(config)
    try:
        pin = manager.generate_child_pin()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Child PIN: {pin} (valid for 15 seconds)")
    return 0


def cmd_claim(config: ControlConfig, args: argparse.Namespace) -> int:
    manager = PinManager(config)
    if args.minutes is not None and args.minutes <= 0:
        print("Minutes must be greater than zero", file=sys.stderr)
        return 1
    allow_until = manager.consume_child_pin(args.pin, args.minutes)
    if not allow_until:
        print("Invalid or expired PIN", file=sys.stderr)
        return 1
    print(f"Access granted until {allow_until.astimezone().isoformat()}")
    return 0


def cmd_revoke(config: ControlConfig, _: argparse.Namespace) -> int:
    manager = PinManager(config)
    manager.revoke_child_access()
    print("Child access revoked")
    return 0


def cmd_override(config: ControlConfig, _: argparse.Namespace) -> int:
    manager = PinManager(config)
    manager.parent_override()
    print("Parent override enabled")
    return 0


def cmd_monitor(config: ControlConfig, args: argparse.Namespace) -> int:
    manager = PinManager(config)
    monitor = ProcessMonitor(config, manager)
    interval = getattr(args, "interval", 5.0)
    monitor.run(interval_seconds=interval)
    return 0


def cmd_scaffold_config(_: ControlConfig, args: argparse.Namespace) -> int:
    output = Path(args.output).expanduser()
    if output.exists():
        print(f"Refusing to overwrite existing file: {output}", file=sys.stderr)
        return 1
    dump_default_config(output)
    print(f"Wrote default config to {output}")
    return 0


def cmd_run_bot(config: ControlConfig, _: argparse.Namespace) -> int:
    manager = PinManager(config)
    bot = ControlBot(config, manager)

    async def runner() -> None:
        await bot.start()
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise
        except KeyboardInterrupt:
            logger = logging.getLogger(__name__)
            logger.info("Bot interrupted by user")
        finally:
            await bot.close()

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        pass
    return 0


_COMMAND_TABLE: dict[str, Callable[[ControlConfig, argparse.Namespace], int]] = {
    "init": cmd_init,
    "status": cmd_status,
    "generate": cmd_generate,
    "claim": cmd_claim,
    "revoke": cmd_revoke,
    "override": cmd_override,
    "monitor": cmd_monitor,
    "scaffold-config": cmd_scaffold_config,
    "run-bot": cmd_run_bot,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if args.command == "scaffold-config":
        return cmd_scaffold_config(ControlConfig(), args)

    try:
        config = _load_config(args.config)
    except FileNotFoundError:
        parser.error(
            f"Configuration file {Path(args.config).expanduser()} not found. "
            "Run `python -m rdcontrol scaffold-config` first."
        )
    handler = _COMMAND_TABLE[args.command]
    return handler(config, args)


if __name__ == "__main__":
    raise SystemExit(main())
