"""
generate_session.py — Interactive script to generate a Pyrogram user session string.

Run this ONCE on your local machine to authenticate your Telegram account.
The printed session string goes into USER_SESSION_STRING in your .env file.

Usage:
    uv run python generate_session.py     # recommended (uses project venv)
    python generate_session.py            # if venv is already activated

Setup (first time only):
    uv venv --python 3.12
    uv pip install -r requirements.txt

What it does:
    1. Asks for your API ID and API Hash (from https://my.telegram.org)
    2. Prompts Telegram to send an OTP to your phone / Telegram app
    3. Optionally asks for your 2FA password if set
    4. Prints the session string — copy it to USER_SESSION_STRING in .env
    5. Immediately terminates the client (session string is self-contained)

Security note:
    - The session string grants full access to your Telegram account.
    - Never share it or commit it to any repository.
    - Store it ONLY in your .env file (which is in .gitignore).
"""

import asyncio
import sys
import os


def _prompt(label: str, secret: bool = False) -> str:
    """Read input from the user, masking input for secrets."""
    if secret:
        import getpass
        value = getpass.getpass(f"{label}: ").strip()
    else:
        value = input(f"{label}: ").strip()
    if not value:
        print(f"[error] {label} cannot be empty.")
        sys.exit(1)
    return value


async def _generate() -> None:
    try:
        from pyrogram import Client
    except ImportError:
        print("[error] pyrotgfork is not installed.")
        print("        Run: pip install pyrotgfork tgcrypto")
        sys.exit(1)

    print()
    print("=" * 60)
    print("  SaveTheFile — Session String Generator")
    print("=" * 60)
    print()
    print("Obtain your API credentials from: https://my.telegram.org")
    print()

    # ── Check .env first for existing credentials ─────────────────────────────
    api_id_env = os.environ.get("TELEGRAM_API_ID", "")
    api_hash_env = os.environ.get("TELEGRAM_API_HASH", "")

    if api_id_env and api_hash_env:
        print(f"Detected credentials in environment:")
        print(f"  API ID   : {api_id_env}")
        print(f"  API Hash : {api_hash_env[:6]}{'*' * (len(api_hash_env) - 6)}")
        use_env = input("Use these? [Y/n]: ").strip().lower()
        if use_env in ("", "y", "yes"):
            api_id = int(api_id_env)
            api_hash = api_hash_env
        else:
            api_id = int(_prompt("API ID"))
            api_hash = _prompt("API Hash", secret=True)
    else:
        api_id = int(_prompt("API ID"))
        api_hash = _prompt("API Hash", secret=True)

    print()
    print("Telegram will send an OTP to your phone or Telegram app.")
    print()

    # ── Generate session string ───────────────────────────────────────────────
    async with Client(
        name="session_generator",
        api_id=api_id,
        api_hash=api_hash,
        in_memory=True,         # no .session file written to disk
    ) as client:
        session_string = await client.export_session_string()
        me = await client.get_me()

    # ── Output ────────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print(f"  Authenticated as: {me.first_name} ({me.phone_number})")
    print("=" * 60)
    print()
    print("Session string (copy this to USER_SESSION_STRING in .env):")
    print()
    print(session_string)
    print()
    print("=" * 60)
    print()

    # ── Optionally write directly to .env ─────────────────────────────────────
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        write = input("Write directly to .env? [y/N]: ").strip().lower()
        if write in ("y", "yes"):
            _patch_env(env_path, "USER_SESSION_STRING", session_string)
            print(f"Written to {env_path}")
    else:
        print(f"No .env file found at {env_path}.")
        print("Copy the session string above and set it manually.")

    print()
    print("Done.  You can now start the bot with: python main.py")
    print()


def _patch_env(path: str, key: str, value: str) -> None:
    """
    Replace the value of KEY= in an existing .env file.
    If the key is not found, append it.
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
            new_lines.append(f"{key}={value}\n")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"\n{key}={value}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


if __name__ == "__main__":
    # Load .env if python-dotenv is available (optional convenience)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    asyncio.run(_generate())
