# Velocis Intelli Agent — Backend

A production-ready FastAPI backend for the Velocis Intelli Agent chatbot with **Cisco AI Defense** guardrails, on-premises LLM support, and **ngrok** tunneling for public exposure — enabling AI Defense red-team / attack-validation testing.

---

## Architecture

### Full Request Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Cisco AI Defense Portal                          │
│                     (Attack Validation / Red-Team)                      │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ POST /v1/chat/completions
                               │ (OpenAI-compatible payload)
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                          ngrok Tunnel                                    │
│              https://<id>.ngrok-free.app  ──►  localhost:8080            │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                       FastAPI Backend (main.py)                          │
│                                                                          │
│   Browser / AI Defense                                                   │
│   ───────────────────                                                    │
│   POST /v1/chat/completions                                              │
│              │                                                           │
│              ▼                                                           │
│   ┌─────────────────────┐     ┌──────────────────────────────────────┐  │
│   │  1. Log raw request  │────►│  SQLite DB (request_logs table)      │  │
│   └─────────┬───────────┘     └──────────────────────────────────────┘  │
│             │                                                            │
│             ▼                                                            │
│   ┌──────────────────────────────────────────────────────────────────┐   │
│   │         2. AI Defense — Inspect USER PROMPT                      │   │
│   │   POST https://<region>.aidefense.security.cisco.com             │   │
│   │         /api/v1/inspect/chat                                     │   │
│   │   Header: X-Cisco-AI-Defense-API-Key: <key>                      │   │
│   └────────────────────────┬─────────────────────────────────────────┘   │
│                            │                                             │
│                    is_safe?│                                             │
│              ┌─────────────┴───────────────┐                            │
│           NO │                             │ YES                         │
│              ▼                             ▼                            │
│   ┌─────────────────────┐     ┌──────────────────────────────────────┐  │
│   │  Return block msg   │     │      3. Call LLM                     │  │
│   │  (content_filter)   │     │                                      │  │
│   └─────────────────────┘     │  • OpenAI   → api.openai.com         │  │
│                               │  • Google   → generativelang…        │  │
│                               │  • Anthropic→ api.anthropic.com      │  │
│                               │  • On-Prem  → http://10.x.x.x:8000   │  │
│                               └──────────────────┬───────────────────┘  │
│                                                  │                      │
│                                                  ▼                      │
│                               ┌──────────────────────────────────────┐  │
│                               │  4. AI Defense — Inspect LLM RESP    │  │
│                               └──────────────────┬───────────────────┘  │
│                                                  │                      │
│                                         is_safe? │                      │
│                                   ┌──────────────┴──────────┐          │
│                                NO │                          │ YES       │
│                                   ▼                          ▼          │
│                        ┌─────────────────┐      ┌───────────────────┐  │
│                        │ Return block msg│      │ Return response   │  │
│                        └─────────────────┘      └───────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Component Map

```
velocis-backend/
├── main.py                  # FastAPI app, lifespan, ngrok startup
├── start.sh                 # One-command startup script
├── requirements.txt         # Python dependencies
├── .env                     # Configuration (secrets — never commit)
├── .env.example             # Template for .env
├── velocis.db               # SQLite database (auto-created)
│
├── app/
│   ├── config.py            # Pydantic-settings — all config from .env
│   ├── database.py          # SQLAlchemy async ORM + table definitions
│   ├── schemas.py           # Pydantic request/response models
│   │
│   ├── routers/
│   │   ├── chat.py          # POST /v1/chat/completions (main endpoint)
│   │   └── config.py        # GET /api/config, /api/health, /api/logs
│   │
│   └── services/
│       ├── defense.py       # Cisco AI Defense inspection calls
│       └── llm.py           # LLM provider routing (OpenAI/Gemini/Claude/OnPrem)
│
└── templates/
    └── index.html           # The chatbot frontend (served by FastAPI)
```

---

## Setup & Deployment

### Prerequisites

- Python 3.11+
- pip / venv
- ngrok account (free tier works) → https://dashboard.ngrok.com

### Step 1 — Clone & Configure

```bash
# Copy the env template
cp .env.example .env
```

Edit `.env` with your values:

```env
# Required — Cisco AI Defense
AI_DEFENSE_API_KEY=your-key-here
AI_DEFENSE_BASE_URL=https://us.api.inspect.aidefense.security.cisco.com

# Required — LLM (choose one provider)
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o

# On-Prem model (shown in frontend UI)
ONPREM_MODEL_NAME=gpt-oss-20b
ONPREM_BASE_URL=http://10.52.1.13:8000/v1

# ngrok (get token from https://dashboard.ngrok.com/auth/your-authtoken)
NGROK_AUTHTOKEN=your-ngrok-token-here
```

### Step 2 — Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3 — Run the Server

```bash
# Option A — convenience script (recommended)
chmod +x start.sh
./start.sh

# Option B — direct
python main.py

# Option C — uvicorn (production)
uvicorn main:app --host 0.0.0.0 --port 8080 --workers 2
```

On startup you will see:

```
========================================================
  🌐  Public URL  :  https://xxxx-xx-xx.ngrok-free.app
  👉  AI Defense red-team endpoint:
      https://xxxx-xx-xx.ngrok-free.app/v1/chat/completions
========================================================
```

### Step 4 — Open the Chat UI

Navigate to **http://localhost:8080** (or the ngrok URL from any device).

---

## ngrok Manual Setup (Alternative)

If you prefer to run ngrok separately:

```bash
# Install ngrok
curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
  | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
  && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
  | sudo tee /etc/apt/sources.list.d/ngrok.list \
  && sudo apt update && sudo apt install ngrok

# Authenticate
ngrok config add-authtoken YOUR_AUTH_TOKEN

# Start tunnel (in a separate terminal)
ngrok http 8080
```

Copy the `Forwarding` URL (e.g. `https://abc123.ngrok-free.app`) — this is your public endpoint.

---

## Cisco AI Defense Integration

### Setting Up Attack Validation

1. Log in to the **Cisco AI Defense portal**
2. Navigate to **Validation → Attack Validation**
3. Create a new validation target with:
   - **Endpoint URL**: `https://<your-ngrok-id>.ngrok-free.app/v1/chat/completions`
   - **Method**: `POST`
   - **Request Format**: OpenAI Chat Completions (compatible)
4. Run the validation suite — AI Defense will send attack prompts directly to your endpoint

### Request Format (AI Defense → Your Backend)

AI Defense sends the standard OpenAI payload:

```json
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "gpt-4o",
  "messages": [
    { "role": "user", "content": "<attack prompt here>" }
  ],
  "stream": false
}
```

Your backend returns a standard OpenAI response:

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1710000000,
  "model": "gpt-4o",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "..." },
      "finish_reason": "stop"
    }
  ],
  "usage": { "prompt_tokens": 10, "completion_tokens": 50, "total_tokens": 60 }
}
```

When blocked by AI Defense:
```json
{
  "choices": [
    {
      "message": { "content": "⚠️ This request was blocked by Cisco AI Defense..." },
      "finish_reason": "content_filter"
    }
  ]
}
```

---

## On-Prem Model

The on-prem model must expose an **OpenAI-compatible** `/v1/chat/completions` endpoint (vLLM, Ollama, LM Studio, or any OpenAI-proxy-compatible server).

Configure in `.env`:

```env
ONPREM_MODEL_NAME=gpt-oss-20b          # or fdtn-ai/Foundation-Sec-8B etc.
ONPREM_BASE_URL=http://10.52.1.13:8000/v1
ONPREM_API_KEY=                         # leave empty if not required
```

In the UI: Settings → Model → Provider → **On-Prem / Custom Server**.

The model name is pulled from the backend `/api/config` endpoint at page load — no manual entry needed in the UI.

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/` | Chatbot UI |
| `POST` | `/v1/chat/completions` | Main chat endpoint (OpenAI-compatible) |
| `GET`  | `/api/health` | Health check |
| `GET`  | `/api/config` | App config (safe — no secrets) |
| `GET`  | `/api/logs` | Audit log (last 100 requests) |
| `GET`  | `/api/stats` | Aggregate statistics |
| `GET`  | `/docs` | Swagger UI |
| `GET`  | `/redoc` | ReDoc |

---

## Database Schema

All data is persisted in `velocis.db` (SQLite):

| Table | Purpose |
|-------|---------|
| `request_logs` | Every inbound request + AI Defense scan results + latency |
| `chat_sessions` | Chat session metadata |
| `chat_messages` | Individual messages with defense scan outcomes |

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_HOST` | `0.0.0.0` | Server bind host |
| `APP_PORT` | `8080` | Server bind port |
| `APP_DEBUG` | `false` | Enable debug/reload mode |
| `AI_DEFENSE_MODE` | `api` | `api` or `gateway` |
| `AI_DEFENSE_API_KEY` | — | Cisco AI Defense API key |
| `AI_DEFENSE_BASE_URL` | US region | Regional base URL |
| `AI_DEFENSE_TIMEOUT_MS` | `15000` | Request timeout |
| `LLM_PROVIDER` | `openai` | `openai`, `google`, `anthropic`, `onprem` |
| `LLM_API_KEY` | — | Provider API key |
| `LLM_MODEL` | `gpt-4o` | Model name |
| `LLM_MAX_TOKENS` | `2048` | Max response tokens |
| `LLM_TEMPERATURE` | `0.7` | Sampling temperature |
| `ONPREM_MODEL_NAME` | `gpt-oss-20b` | On-prem model identifier |
| `ONPREM_BASE_URL` | `http://10.52.1.13:8000/v1` | On-prem server URL |
| `ONPREM_API_KEY` | — | On-prem server key (if any) |
| `NGROK_AUTHTOKEN` | — | ngrok authentication token |
| `NGROK_DOMAIN` | — | Fixed ngrok domain (paid plan) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./velocis.db` | SQLite path |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
