# TelegramBot — Multi-group Hashtag Relay

Public, self-hostable Telegram bot that relays messages from **group owners or administrators** to their chosen Telegram channels if an approved hashtag appears.

## Features

- Different Telegram groups can independently configure different target channels and hashtags.
- Fully in-Telegram group/channel selection; no chat IDs required.
- Source admins only can configure or modify routes.
- Messages from regular group members are ignored.
- Source group and destination channel rights verified with Telegram before settings are saved.
- SQLite persistence across container restarts.
- Long polling, no public HTTP ports required.
- Text messages and single media messages with hashtags in captions can be copied.

## Quick start (Ubuntu + Docker)

```bash
git clone https://github.com/devaeterne/TelegramBot.git
cd TelegramBot
cp .env.example .env
nano .env          # set BOT_TOKEN
docker compose up -d --build
docker compose logs -f --tail=50
```

The `telegram_relay_data` Docker volume holds the SQLite database. **Do not delete the volume when updating**.

## Setup from Telegram

1. Add the bot as an **administrator** in your Telegram group.
2. Add the bot as an **administrator** in your target channel with **Post Messages** rights.
3. Open a **private chat** with the bot and send `/setup`.
4. Use the Telegram chat picker to choose the **source group**.
5. Use the Telegram chat picker to choose the **destination channel**.
6. Send a comma-separated hashtag list, e.g. `Analiz,Kar,Proje`.
7. Send `#Analiz` in the group as an administrator to test delivery. Regular members' messages will not be delivered.

Each group may configure its own route and list, independently of other groups.

### Commands

| Where | Command | Description |
|---|---|---|
| Private chat | `/start` | Instructions |
| Private chat | `/setup` | Create/update group→channel route |
| Private chat | `/cancel` | Cancel pending setup |
| Source group | `/status` | Show current route (admin only) |
| Source group | `/hashtags Analiz,Kar,Proje` | Replace allowed hashtags (admin only) |
| Source group | `/disable` | Pause relay (admin only) |

Re-run `/setup` to re-enable a disabled route or change the destination channel.

## Security model

- Anonymous group-admin messages are accepted only if Telegram attributes the sender to the exact source group. The actual human cannot be identified or verified.

- Chat picker selections are **not authorization**. Actual Telegram admin memberships are checked independently.
- Bot must be an admin in the source group; destination channel must grant it message-posting rights.
- Current user must be an admin in both chats to finish setup.
- Publishing requires the sender's current source-group admin status. API errors fail closed.
- Anonymous admins posting as the source group are supported; their human identity cannot be verified. Posts as other chats/channels and ordinary bot accounts are excluded.
- Configuration is per group; only identifiable administrators in that group can change it. Anonymous group posts cannot issue management commands.
- A person who is an admin in both a group and channel can configure routing between them; review who you grant admin privileges to.
- Do not commit the token. The `.env` file is ignored by Git.

## Development

```bash
python3 -m unittest discover -s tests -v
```

Install Python dependencies to run the actual bot: `pip install -r requirements.txt`.

## Limitations (v2)

- One destination per source group. Multiple groups can share one channel.
- Album entries arrive separately and may be copied as separate posts.
- Existing/historical messages are not replayed. Edited messages are not synchronized.
- Setup state is held in memory during the picker workflow (start `/setup` again after a restart).
- sqlite is designed for **one polling process** and a modest bot workload.
- Telegram may refuse to copy protected or unsupported messages; failures are logged.
- Role checks reflect current role at processing time, not necessarily at posting time.
- No web panel, billing, advanced moderation, or delivery/retry ledger in v2.

## License

No license has been granted yet. Public GitHub visibility alone does not grant reuse, modification or redistribution rights. Add an explicit open-source license if you intend others to deploy or extend the bot.
