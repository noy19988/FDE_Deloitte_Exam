# Airport Investment Intelligence Agent

An AI agent that helps investment analysts find **US airports where expansion would be most profitable**.
Ask in plain language (typing or voice) – for example:

- *Which airports in New England are strong candidates for terminal expansion?*
- *Compare LA and Santa Ana airport congestion levels.*
- *What is the percentage of long haul flights out of Anchorage airport?*
- *What is the unmet flight demand in SFO airport and why?*

The agent uses public US DOT and FAA data. **Scores are computed by deterministic Python code** – the LLM
(Gemini, via Google ADK) understands the question, calls the right tool and explains the result, and an
automatic check flags any number in the answer that did not come from the data.

See **[DESIGN.md](DESIGN.md)** for the scoring methodology, tradeoffs and where AI is used.

---

## Run it

You need **Docker** and a **Gemini API key**.

1. **Get a Gemini API key** at <https://aistudio.google.com/apikey> (free to create).
2. **Create a file named `.env`** in the project folder with your key (replace `your-key`):
   ```bash
   echo "GOOGLE_API_KEY=your-key" > .env
   ```
   That is the only required setting. Optional ones are listed under *Settings* below.
3. **Start everything** (PostgreSQL, backend, UI):
   ```bash
   docker compose up --build
   ```
4. Open **<http://localhost:8501>** and ask a question.

The first answer takes ~20–40 seconds: the tools call the live US DOT API.

| Service | Address |
|---|---|
| Chat UI (Streamlit) | <http://localhost:8501> |
| Backend API (FastAPI) – interactive docs | <http://localhost:8001/docs> |
| PostgreSQL | `localhost:5433` (user / password / db: `airport`) |

To stop: `docker compose down`. Conversations are kept in a Docker volume;
`docker compose down -v` deletes them too.

### Settings (`.env`)

| Variable | Required | Default |
|---|---|---|
| `GOOGLE_API_KEY` | **yes** | – |
| `GEMINI_MODEL` | no | `gemini-3.5-flash` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | no | `airport` |
| `POSTGRES_HOST`, `POSTGRES_PORT` | no | `localhost`, `5433` (only used when running without Docker) |

### Notes
- **Gemini limits:** on the free tier a project gets a small number of requests per day. If you see
  *"The AI model is busy right now"*, wait a minute (Google sometimes returns "high demand"), or check
  your quota/billing in Google AI Studio.
- **Voice input:** press the microphone inside the chat box. The browser asks for microphone permission.
  The recording becomes text in the box – check it and press send.
- **Ports:** if 8501, 8001 or 5433 are taken on your machine, change the left side of `ports:` in `docker-compose.yml`.

---

## Run without Docker (development)

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r frontend/requirements.txt
docker compose up -d db                                  # only the database
.venv/bin/uvicorn backend.main:app --port 8001           # backend
.venv/bin/streamlit run frontend/app.py                  # UI (uses http://localhost:8001)
```

---

## Project layout

```
backend/
  main.py              FastAPI: /chat, /sessions, /transcribe
  config.py            years, thresholds, default weights, database URL
  agent/               ADK agent, system prompt (instructions.md), automatic number check
  tools/               the 7 tools the agent can call
  scoring/             all the math: metrics, percentiles, scores, special metrics
  data_sources/        live DOT and FAA API clients
  db/                  load data/processed/*.csv into PostgreSQL
frontend/app.py        Streamlit chat UI (talks only to the backend)
etl/                   scripts that built data/processed/ from BTS and OurAirports downloads
data/processed/        small pre-processed tables (included – no need to run the ETL)
DESIGN.md              design document
```

## Rebuild the pre-processed data (optional)

Not needed to run the project. The scripts download large public files (BTS On-Time, BTS T-100 Segment,
OurAirports) into `data/raw/` and write the small tables to `data/processed/`:

```bash
.venv/bin/python etl/airports.py
.venv/bin/python etl/delays.py
.venv/bin/python etl/routes.py
```

## Data sources

- US DOT / BTS **T-100** (passengers, seats, departures) – live API, `data.bts.gov`
- DOT **Consumer Airfare Report, Table 7** (fare premium) – live API, `data.transportation.gov`
- **FAA NAS Status** (live ground stops and delays) – `nasstatus.faa.gov`
- BTS **On-Time Reporting** (taxi-out, cancellations, NAS delays) – pre-processed
- BTS **T-100 Segment, all carriers** (distance and cargo/passenger class) – pre-processed
- **OurAirports** (runways) – pre-processed
