# Telegram Hashtag Relay

A lightweight Telegram group-to-channel relay. Only messages from group **owners** or **administrators** containing approved hashtags are copied to the configured channel. Messages from regular members never pass.

## Rules
- One configured source group and one destination channel.
- Configurable case-insensitive hashtags, e.g. `#Analiz`, `#Kar`, `#Proje`.
- Telegram API role verification for each qualifying message (fail closed).
- Reject anonymous-admin / sender-chat and bot messages.
- Copy messages without a forwarded-from header. Supports text and individual media messages with hashtags in captions.
- Does not relay messages posted before startup. Albums may be split into individual channel posts.

## Configuration

Copy `.env.example` to `.env` on the **server**, and set real values there. Never commit credentials.

```bash
cp .env.example .env
nano .env
docker compose up -d --build
docker compose logs -f --tail=50
```

Grant the bot administrator status in the source group (for reliable role checks and message visibility). In the destination channel, grant the bot permission to post messages. Use the numeric group/channel IDs (usually start with `-100`).

## Deploy from private GitHub repository

Provision an SSH deploy key with **read-only** repository access on the Ubuntu server. Then:

```bash
git clone git@github.com:devaeterne/TelegramBot.git
cd TelegramBot
cp .env.example .env
nano .env
docker compose config --quiet
docker compose up -d --build
docker compose ps
```

Update:

```bash
git pull --ff-only origin main
docker compose up -d --build
```

## Local test

```bash
python3 -m unittest discover -s tests -v
```

## Operational notes

- Uses polling; no inbound port or reverse proxy required.
- Run **one** polling instance per bot token.
- Role is checked at processing time, not message creation time.
- Telegram may prohibit copying protected content or service messages. Failures are logged.
- No persistent storage in v1; retries after downtime or delivery auditing are outside current scope.
