# rdcontrol

`rdcontrol` is a proof-of-concept parental control toolkit designed to be
extensible rather than intrusive. It combines three core building blocks:

* **Process monitoring** – automatically terminates blocked applications when
  no valid child session is active.
* **PIN management** – separates a long-lived parent PIN from short-lived child
  PINs that expire after 15 seconds and convert into timed access windows.
* **Telegram bot control** – optional remote management layer powered by the
  official Telegram Bot API.

## Features

* YAML-based configuration with configurable process blocklists
* Secure PIN storage backed by PBKDF2 hashing
* Command-line utilities for day-to-day operations
* Telegram bot commands for remote management (`/pin`, `/grant`, `/revoke`,
  `/status`, `/override`)
* Process monitor loop that enforces the blocklist whenever the child has no
  active allowance

## Installation

1. Create and activate a Python 3.11 virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Scaffold a default configuration file and set an initial parent PIN:

   ```bash
   python -m rdcontrol scaffold-config
   python -m rdcontrol init --parent-pin <your-secure-pin>
   ```

4. Edit the generated config file (default: `~/.config/rdcontrol/config.yaml`)
   to match your desired blocklist and Telegram settings.

## Command line usage

Run commands via `python -m rdcontrol <command>`:

* `status` – show remaining child time.
* `generate` – create a temporary child PIN (15 seconds validity).
* `claim <PIN>` – convert a short-lived PIN into an active session using the
  default time allowance (or override with `--minutes`).
* `revoke` – immediately remove the child’s access.
* `override` – grant a parent override (effectively unlimited access until
  revoked).
* `monitor` – start the background process monitor that terminates blocked
  applications.
* `run-bot` – launch the Telegram bot for remote control.

## Process monitoring

The monitor uses `psutil` to inspect running processes. When the child has no
remaining time, it will terminate any process whose name matches an entry in the
`blocklist` array from the configuration file. Consider running this command at
startup using the operating system’s scheduler or service manager.

## Telegram bot setup

Set `telegram_bot_token` and `telegram_parent_chat_ids` in the YAML configuration.
The bot restricts commands to the listed chat IDs. A typical workflow is:

1. Parent issues `/grant 45` in Telegram. The bot responds with a short PIN.
2. Parent relays the PIN to the child. The child runs `python -m rdcontrol claim
   <PIN>` within 15 seconds.
3. The CLI grants 45 minutes of access. The monitor permits play until the time
   expires.
4. Parent can revoke with `/revoke` or extend via `/grant` again.

## Security considerations

* Parent PINs are stored using PBKDF2 hashing and never written in plain text.
* Child PINs expire quickly to reduce the risk of leakage.
* Configuration and PIN stores live under `~/.config/rdcontrol/`; secure this
  directory with appropriate filesystem permissions.
* Remote deletion or shutdown should be orchestrated through the Telegram bot by
  adding custom commands as needed.

## Disclaimer

This project is a starting point. Thoroughly audit and harden the code before
using it in production environments. Consider additional controls (firewalling,
DNS filtering, system account restrictions) to complement software safeguards.
