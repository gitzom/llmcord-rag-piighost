# llmcord-rag-piighost

Fork of [jakobdylanc/llmcord](https://github.com/jakobdylanc/llmcord) with two extras: local RAG memory and PII anonymization.

Mention the bot to start a thread, reply to keep it going, `/model` to switch models. On top of that:

- Past chats get pulled in from a local LanceDB store built from your own history. Top 5 chunks per message, added to the system prompt.
- All LLM traffic goes through a self-hosted piighost-API proxy in Docker. It swaps names, emails, phones and similar for placeholders like `<<PERSON:1>>` before anything leaves your machine, then puts the real values back in the reply.
- Exchanges are buffered per channel and written to `logs/<channel_id>_<timestamp>.jsonl` after 30 minutes with no activity. Those logs are not fed back into the DB automatically.

I run the bot itself on bare metal (Windows 11 in my case). Only piighost runs in Docker. Search happens locally on plaintext, piighost sits between llmcord and the upstream LLM API.

## What changed from upstream

| File | Change |
| --- | --- |
| `db.py` | LanceDB wrapper: `BAAI/bge-small-en-v1.5` embeddings, chunking, vector and full-text search, async wrappers. |
| `db_firsttime_init.py` | Rebuilds the DB from `data/dense_rag_memories.txt` (wipes `./lancedb`). |
| `llmcord.py` | RAG lookup in `build_system_message()`, reasoning token capture, per-channel logging, `/model` opened to everyone. |
| `compose.yaml`, `pipeline.toml` | piighost-API service config. |

Upstream only lets admins use `/model`. There is a comment in `model_command` if you want that check back.

## Setup

### 1. Install

```bash
git clone https://github.com/gitzom/llmcord-rag-piighost
cd llmcord-rag-piighost
python -m pip install -r requirements.txt
python -m pip install lancedb sentence-transformers
```

It still runs without the RAG packages, it just skips memory lookup and warns at startup.

### 2. Secrets

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

No credentials in `config.yaml`. Keys ending in `_env` are read from `.env`, for example `bot_token_env: DISCORD_BOT_TOKEN`. You need a Discord bot token with MESSAGE CONTENT INTENT enabled, plus the client ID.

### 3. Build the memory DB

Put your own memories in `data/dense_rag_memories.txt`. Entries are split on a line with `---` (a `==== CONVO ===` line works too):

```text
[friend]: remember the pier trip?
[me]: yeah, go again this summer
---
[friend]: wifi password is hunter2
```

Then:

```bash
python db_firsttime_init.py   # wipes and rebuilds ./lancedb
python db.py                  # optional self-test
```

First run pulls the embedding model (about 130 MB). After that you can set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` in `.env`. The bot only reads the DB, so new memories have to be added by hand for now.

### 4. Start the piighost proxy

```bash
docker pull ghcr.io/athroniaeth/piighost-api:latest
docker run --rm ghcr.io/athroniaeth/piighost-api:latest /app/.venv/bin/keyshield generate
# put the output in .env as API_KEY_DEV
docker run --rm ghcr.io/athroniaeth/piighost-api:latest /app/.venv/bin/keyshield pepper
# put the output in .env as SECRET_PEPPER
docker compose up -d
```

`NANOGPT_API_KEY` is your upstream LLM key, forwarded through the proxy. `API_KEY` guards the proxy REST endpoints. `API_KEY_DEV` and `SECRET_PEPPER` are piighost auth. First start also pulls the GLiNER model (about 500 MB), so give it a few minutes and check `http://127.0.0.1:8000/health`. If the proxy is down, LLM calls fail.

### 5. Run

```bash
python llmcord.py
```

The invite URL prints at startup. `config.yaml` reloads on each message, so most tweaks do not need a restart.

## Layout

| Path | Purpose |
| --- | --- |
| `llmcord.py` | Discord bot: events, streaming, RAG, logging. |
| `db.py`, `db_firsttime_init.py` | Vector store and DB builder. |
| `config.yaml`, `.env.example` | Settings and secrets template. |
| `compose.yaml`, `pipeline.toml` | piighost server config. |
| `data/`, `lancedb/`, `logs/` | Memory source, vector DB, conversation logs. |

## Notes

- Top 5 retrieval is hardcoded in `build_system_message()`.
- Logs keep timestamp, channel/guild/user IDs and names, message, model, reasoning text, and response.
- `pipeline_llm.toml` is not used. To use it, mount it as `/app/pipeline.toml` in `compose.yaml`.
- Discord user IDs get flagged as `CREDIT_CARD`.

## TODO

- Keep pseudonyms stable through a conversation by passing a constant `thread_id`.
- Link entities that mean the same person (USERNAME, PERSON, USER_ID).
- Embed `logs/*.jsonl` back into LanceDB automatically.

## AI use

I used AI to help draft this README and for small cleanups like renames and formatting. Everything else is hand-written.

## Credits

- [jakobdylanc/llmcord](https://github.com/jakobdylanc/llmcord) (MIT), the base bot
- [Athroniaeth/piighost](https://github.com/Athroniaeth/piighost) and [piighost-api](https://github.com/Athroniaeth/piighost-api), anonymization
- [LanceDB](https://lancedb.github.io) and [sentence-transformers](https://www.sbert.net), vectors and embeddings
