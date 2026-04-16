<div align="center">

# TeleFlow

**Telegram Restricted Media Saver Bot**

Snag media from any Telegram channel — public, private, or restricted —
and deliver it straight to your chat or a destination channel.
No forwarding restrictions, no limits, just the file.

<br/>

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![Pyrogram](https://img.shields.io/badge/PyroTGFork-2.2-2CA5E0?style=flat-square&logo=telegram&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-Motor-47A248?style=flat-square&logo=mongodb&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

</div>

## [+] How It Works

> Paste a `t.me` post link → Bot fetches the message via user session → Downloads media → Re-uploads to your chat

The bot uses a dual-client architecture — a **bot account** for sending/uploading and a **user account session** for accessing restricted or private channels that the bot itself cannot join.

## [+] Features

- **Restricted & private channels** — bypasses forwarding restrictions using a user session
- **All media types** — videos, documents, photos, audio, voice, animations, stickers
- **Topic / thread links** — supports `t.me/c/chat/topic/msg` format
- **Batch transfers** — range syntax `t.me/channel/100-110` to grab multiple posts at once
- **Custom destination** — forward files to any channel instead of the current chat
- **Custom thumbnail** — set your own default thumbnail for all transfers
- **Filename templates** — rename files using `{filename}`, `{date}`, `{chat}`, `{id}`, `{ext}`
- **Caption control** — custom caption templates and word filter/strip rules
- **Concurrent workers** — async worker pool handles multiple tasks simultaneously
- **Persistent tasks** — MongoDB-backed task tracking with status history
- **Crash recovery** — interrupted tasks are marked on restart, visible in `/tasks`

## [+] Setup

<details>
<summary><strong>1. Get Telegram credentials</strong></summary>

<br/>

1. Go to [my.telegram.org](https://my.telegram.org) → API Development Tools
2. Create an app and copy your **API ID** and **API Hash**
3. Create a bot via [@BotFather](https://t.me/BotFather) and copy the **Bot Token**

</details>

<details>
<summary><strong>2. Generate a session string</strong></summary>

<br/>

The user session is required to access restricted channels.

```bash
uv run python generate_session.py
```

Follow the prompts — it will ask for your phone number and OTP, then print the session string. Copy it to `USER_SESSION_STRING` in your `.env`.

> The session string grants full access to your Telegram account. Never share it or commit it.

</details>

<details>
<summary><strong>3. Configure environment</strong></summary>

<br/>

```bash
cp .env.example .env
```

Fill in your values:

```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
USER_SESSION_STRING=your_session_string

MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
SUDO_USERS=your_telegram_user_id
```

</details>

<details>
<summary><strong>4. Install & run</strong></summary>

<br/>

```bash
# Install dependencies
uv sync

# Start the bot
uv run python main.py
```

</details>

## [+] Usage

**Single post**
```
t.me/channel/123
t.me/c/1234567890/45
t.me/b/botname/78
```

**Range of posts**
```
t.me/channel/100-110
```

**Topic / thread link**
```
t.me/c/1234567890/55/93
```

**Join a private chat first**
```
t.me/+AbCdEfGhIj
```
Send the invite link, then send the post link.

## [+] Commands

| Command | Description |
|---|---|
| `/start` | Welcome screen |
| `/help` | Usage guide |
| `/settings` | Per-user settings (destination, thumbnail, filename, caption) |
| `/tasks` | Recent task history |
| `/status` | Active tasks |
| `/system` | System info and worker status |
| `/cancel <id>` | Cancel a running task |
| `/adduser <id>` | Grant access to a user |
| `/removeuser <id>` | Revoke access |
| `/users` | List authorised users |

## [+] License

This project is licensed under the [MIT License](LICENSE).

<br/>

<div align="center">

Built with ❤️ by **Avishkar Patil**

</div>
