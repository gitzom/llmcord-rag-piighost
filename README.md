# llmcord-rag-piighost

> A personal fork of [jakobdylanc/llmcord](https://github.com/jakobdylanc/llmcord). Talk to LLMs with your friends on Discord, with **long-term RAG memory** and **PII anonymization** bolted on.

llmcord turns Discord into a collaborative LLM frontend: @ the bot to start a conversation, reply to continue the thread, `/model` to switch models. This fork adds:

- **Long-term memory (RAG).** A local [LanceDB](https://lancedb.github.io) vector store built from your own conversation history. On every message, the bot retrieves the top-5 most similar memory chunks from embedded text, and appends them to the system prompt.
- **PII anonymization.** Every LLM request goes through a self-hosted [piighost-API](https://github.com/Athroniaeth/piighost) server (Docker) that replaces names, emails, phone numbers, etc. with stable placeholders (`<<PERSON:1>>`) *before* anything leaves your machine. The server restores the real values in the reply. (Placeholder consistency across conversations is still TODO. See [ROADMAP.md](ROADMAP.md).)
- **Conversation logging.** Exchanges are buffered per channel and flushed to `logs/<channel_id>_<timestamp>.jsonl` after 30 minutes of inactivity. These logs are **not** embedded back into the vector DB automatically (still a TODO). The memory corpus is curated by hand.
- **Reasoning capture.** Thinking/reasoning tokens streamed separately by some providers (`reasoning_content`) are captured into the logs.

The bot itself runs on bare metal (Windows, in my case). Only the piighost anonymization server runs in Docker.

Memory retrieval and anonymization are independent layers: the vector search happens locally on plaintext, while the piighost-API server sits in-between llmcord and the upstream API (which hosts the actual LLM you're trying to use). Both the piighost-API and llmcord run on your device so all text with PII stays on your device (if everything is working correctly).

## What changed vs. upstream llmcord

| File | Change |
| --- | --- |
| `db.py` | LanceDB wrapper: `BAAI/bge-small-en-v1.5` sentence-transformer embeddings, chunking, vector + full-text search, and async wrappers (`asyncio.to_thread`) so the event loop never blocks. |
| `db_firsttime_init.py` | Wipes and rebuilds the vector DB from `data/dense_rag_memories.txt`. |
| `llmcord.py` | `build_system_message()` now awaits RAG retrieval and appends a `Relevant long-term memories` block with `[memory score]` chunks; reasoning-token capture; per-channel conversation logging with a 30-minute inactivity flush; `/model` opened up to everyone (not just server admins). |
| `compose.yaml` | The piighost-api service Docker Compose file. |
| `pipeline.toml` | piighost-api configs.|

**Note on `/model`:** upstream restricts model switching to configured admin IDs; I opened it to anyone who can talk to the bot. To restore the admin check, see the comment inside `model_command` in `llmcord.py`.

## Setup

### 1. Clone and install

```bash
git clone https://github.com/gitzom/llmcord-rag-piighost
cd llmcord-rag-piighost
python -m pip install -r requirements.txt

python -m pip install lancedb sentence-transformers
```

Without the RAG packages the bot still runs fine. It just skips memory retrieval and prints a warning at startup.

### 2. Configure secrets

```bash
cp .env.example .env   # Windows: copy .env.example .env
```

`config.yaml` never contains credentials. Any setting can read from an environment variable by appending `_env` to its name. The value is looked up in `.env` at startup (via python-dotenv):

```yaml
bot_token_env: DISCORD_BOT_TOKEN   # reads DISCORD_BOT_TOKEN from .env
client_id_env: DISCORD_CLIENT_ID
```

At minimum you need a [Discord bot token](https://discord.com/developers/applications) (enable **MESSAGE CONTENT INTENT** under the Bot tab) and the app's client ID (OAuth2 tab).

### 3. Build your own vector database

The bot's memories come from **your own data**. You're meant to build your own database, styled however you like.

The bot only ever *reads* the vector DB. Its `logs/*.jsonl` conversations are **not** embedded automatically (that pipeline is still TODO). You have to add new memories to the database by hand.

Create `data/dense_rag_memories.txt`, a plain-text file where each memory entry is separated by a line containing `---` (a `==== CONVO ===` line also acts as a separator). Each entry becomes one embedded chunk:

```text
[friend]: remember the pier trip?
[me]: yeah, we should go again this summer
---
[friend]: the wifi password is hunter2
[me]: never forgetting that
---
```

Then build the database (**this wipes and rebuilds `./lancedb` from scratch**):

```bash
python db_firsttime_init.py
```

The first run downloads the embedding model (`BAAI/bge-small-en-v1.5`, ~130 MB) from Hugging Face. Once it's cached you can set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` in `.env` to skip the network checks at startup. `python db.py` runs a quick self-test search.

Rebuilding wipes and recreates `./lancedb`, which means you don't have to init every time. Just restart the bot.

### 4. Start the anonymization proxy (Docker)

The proxy needs an API key and a pepper. Both are generated using the piighost image. To generate them, run the two following `docker run --rm` commands:

```bash
docker pull ghcr.io/athroniaeth/piighost-api:latest

docker run --rm ghcr.io/athroniaeth/piighost-api:latest /app/.venv/bin/keyshield generate
# -> Set in your .env : "API_KEY_DEV=ak_v1-…"

docker run --rm ghcr.io/athroniaeth/piighost-api:latest /app/.venv/bin/keyshield pepper
# -> Set in your .env : "SECRET_PEPPER=…"
```

Put both printed values into `.env`. They're read by `compose.yaml`; the server refuses to start without them (or an explicit `PIIGHOST_ALLOW_ANONYMOUS=true` opt-in).

Then start it:

```bash
docker compose up -d
```

The first start also downloads the GLiNER detection model (~500 MB). Give it a few minutes, then check readiness at `http://127.0.0.1:8000/health`.

How the keys are used in my setup:

- `NANOGPT_API_KEY` is your **upstream provider key** (nano-gpt.com for me). The bot sends it to the proxy, which forwards it upstream. This is `providers.nanogpt.api_key_env` in `config.yaml`.
- `API_KEY` is the keyshield key protecting the proxy's direct REST endpoints (`/v1/anonymize`, `/v1/deanonymize`, …), loaded as `API_KEY_default` by compose. Reuse your `API_KEY_DEV` value or generate a second key.
- `API_KEY_DEV` / `SECRET_PEPPER` is required by piighost-API. It's used for authentication to the piighost-API specifically.


### 5. Run the bot

```bash
python llmcord.py
```

@ the bot in Discord to start a conversation; reply to continue. The invite URL prints at startup (needs `client_id` set). `config.yaml` hot-reloads on each message, so most setting changes don't need a restart.

## Project layout

| Path | Purpose |
| --- | --- |
| `llmcord.py` | The Discord bot, which handles discord events, reply chains, streaming responses, RAG injection, and conversation logging.|
| `db.py` | Vector store: embeddings, chunking, search, async wrappers.|
| `db_firsttime_init.py` | Build `./lancedb` from dense_rag_memories.txt |
| `config.yaml` | Bot settings, contains variables pertaining to the upstream API and the discord bot. |
| `.env.example` | The file you must fashion your .env file after.
| `compose.yaml` | Docker Compose file piighost-api server. You can adjust it according to the [piighost-API docs](https://docs.piighost.dev/en/guide/reference/api-cli/). |
| `pipeline.toml` | piighost detector configurations |
| `data/` | The memory data that is embedded into the vector database (`dense_rag_memories.txt`).|
| `lancedb/` | Generated vector database. |
| `logs/` | Conversation logs (`.jsonl`). |

## Notes and quirks

- Tested on Windows 11 / Python 3.14 with the bot on bare metal. The `Dockerfile` comes from llmcord and isn't used/hasn't been tested here.  `compose.yaml` is for the piighost-API.
- Memories are injected into the system prompt and selecting specifically the top-5 is hardcoded in `build_system_message()`.
- Conversation log entries contain: timestamp, channel/guild/user IDs and names, the user message, the model, reasoning text (can be empty), and the response.
- If the proxy isn't running, the bot's LLM calls will fail.
- pipeline_llm.toml doesn't work, but if you wanted to use it you'd mount `./pipeline_llm.toml:/app/pipeline.toml` instead of `pipeline.toml` in `compose.yaml`.
- Discord user IDs are detected as `CREDIT_CARD`.

## TODO

- **Stable pseudonyms across a conversation.** Pseudonyms for the same person can vary from request to request, because a constant thread_id is not passed in to piighost-API for each request.
- **Pseudonym unification via GLiNER entity linking.** Contextual linking is not implemented: recognizing that a USERNAME, a PERSON and a USER_ID all denote the same human. 
- **Auto-embed conversations into the vector DB.** The `logs/*.jsonl` conversation logs are never written back into LanceDB.



## Credits

- [jakobdylanc/llmcord](https://github.com/jakobdylanc/llmcord). The base Discord bot (MIT)
- [Athroniaeth/piighost](https://github.com/Athroniaeth/piighost) & [piighost-api](https://github.com/Athroniaeth/piighost-api) . PII anonymization library and API server
- [LanceDB](https://lancedb.github.io) + [sentence-transformers](https://www.sbert.net) . Vector store and embeddings
