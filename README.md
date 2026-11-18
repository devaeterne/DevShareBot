# DevShareBot — Multi-group Hashtag Relay & Request Router

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
git clone https://github.com/devaeterne/DevShareBot.git
cd DevShareBot
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

## Member requests: group → group

A separate workflow supports requests from **all human group members**, independently from admin-only group → channel publishing.

1. Add the bot as admin in **both** source and destination groups.
2. A Telegram account that is admin in **both groups** opens the bot's private chat and sends `/setuptalep`.
3. Choose the source group and then a **different** destination group.
4. Any source group member can send `#Talep XAUUSD` or `#Talep BTC` at the **beginning** of a text message.
5. The bot copies the original message into the request group. Only after successful copying, it replies to the original message: `✅ Talebiniz alınmıştır.`

`#Talep` with no details receives a usage hint and is not delivered. Regular members cannot change destinations. Source and destination must be different groups. Bot-generated messages, messages sent on behalf of other chats, and channel discussion echoes are excluded; anonymous posts attributed to the source group are supported. For security, setup validates both groups' admins using Telegram.

Each source group has one independent request target, separate from its existing publication channel. The request destination is not required to be a public channel; it is a Telegram group. The destination receives a message copy (no reliable original author attribution from `copyMessage`); avoid placing sensitive data in public request groups.

Request copying is best-effort (no retry queue/deduplication in this version). The confirmation is sent only when Telegram reports copying succeeded, though the reply itself may fail if the bot lacks send permissions.

### Commands

| Where | Command | Description |
|---|---|---|
| Private chat | `/start` | Instructions |
| Private chat | `/setup` | Create/update group→channel route |
| Private chat | `/setuptalep` | Configure group→request-group route |
| Private chat | `/cancel` | Cancel pending setup |
| Source group | `/status` | Show current route (admin only) |
| Source group | `/hashtags Analiz,Kar,Proje` | Replace allowed hashtags (admin only) |
| Source group | `/disable` | Pause relay (admin only) |
| Source group | `/talepstatus` | Show request destination (admin only) |
| Source group | `/talepkapat` | Disable requests (admin only) |

Re-run `/setup` to re-enable a disabled route or change the destination channel.

## Security model

- Anonymous group-admin messages are accepted only if Telegram attributes the sender to the exact source group. The actual human cannot be identified or verified.

- Chat picker selections are **not authorization**. Actual Telegram admin memberships are checked independently.
- Bot must be an admin in the source group; destination channel must grant it message-posting rights.
- Current user must be an admin in both chats to finish setup.
- Publishing requires the sender's current source-group admin status. API errors fail closed.
- Anonymous admins posting as the source group are supported; their human identity cannot be verified. Posts as other chats/channels and ordinary bot accounts are excluded.
- Configuration is per group; only identifiable administrators in that group can change it. Request setup additionally requires admin rights in the destination group. Anonymous group posts cannot issue management commands.
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
