# Airport Investment Intelligence Agent – Design

## 1. Goal and how we read it

The firm invests in US airport modernization and wants to find airports where renovation would be
most profitable "based on increased flight and passenger capacity".

We have no construction-cost or revenue data, so we **do not compute profit**. We measure the thing that
makes expansion pay off: **demand that is larger than (or growing faster than) the airport's capacity**.
The agent ranks and compares airports on that, explains why, and says clearly what it cannot know.

## 2. Architecture

```
 Streamlit chat UI  ──HTTP──►  FastAPI backend  ──►  ADK agent (Gemini)
 (text + voice)                 /chat /sessions        │  chooses a tool, explains the result
                                /transcribe            ▼
                                                 7 Python tools  ──►  deterministic scoring (pandas)
                                                       │                    │
                                                       │           ┌────────┴─────────┐
                                                       ▼           ▼                  ▼
                                              FAA status (live)  DOT API (live)   PostgreSQL
                                                                 traffic, fares   pre-processed BTS /
                                                                                  OurAirports tables
                                                                                  + saved conversations
```

- **frontend/** – Streamlit, ChatGPT-style: chat list, one input box with a microphone, RTL/LTR per language.
  It has no logic; it only calls the backend.
- **backend/main.py** – FastAPI: conversations, chat, voice transcription.
- **backend/agent/** – ADK `Agent` + system prompt + the automatic number check.
- **backend/tools/** – the 7 tools the LLM can call. They return plain JSON.
- **backend/scoring/** – all the math. No LLM here.
- **etl/** – scripts that turned large BTS / OurAirports downloads into small tables (`data/processed/`).
- Everything runs with `docker compose up` (PostgreSQL, backend, frontend).

## 3. Data sources

| Data | Source | How we get it | Why this way |
|---|---|---|---|
| Passengers, seats, departures per airport per year (2014–2025) | US DOT T-100 (`data.bts.gov`, Socrata) | **Live API**, summed on their side with SoQL | Small result, always current |
| Fare premium per airport | DOT Consumer Airfare Report, Table 7 (`data.transportation.gov`) | **Live API** | Same |
| Ground stops / delay programs right now | FAA NAS Status | **Live API** (XML) | Real-time by nature |
| Taxi-out time, cancellations, NAS delays | BTS On-Time Reporting (12 monthly files) | **Pre-processed** (`etl/delays.py`) | Millions of flight rows; no API offers airport-level yearly aggregates |
| Flights by distance and class (long-haul, cargo) | BTS T-100 Segment, all carriers | **Pre-processed** (`etl/routes.py`) | Download-only (a web form); no API |
| Runways (open, ≥5,000 ft) | OurAirports | **Pre-processed** (`etl/airports.py`) | Static reference data |

We checked other public APIs (OpenSky, Aviationstack): they give flights or positions, not the airport-level
yearly statistics we need, so they were not used. The reviewer never has to run the ETL – its output is in
`data/processed/` and is loaded into PostgreSQL when the backend starts.

**Scope:** airports in the 50 US states with at least **100,000 departing passengers in 2025**
(`MIN_PASSENGERS` in `backend/config.py`) – 227 airports, **99.25% of all departing passengers**.
Below that, data is thin (On-Time covers large airlines only; the fare table covers ~200 airports) and tiny
airports would distort the percentiles everyone else is ranked against. Asking about a smaller airport
returns its real number, e.g. *"PSM had 85,102 departing passengers in 2025, below our threshold"*.

## 4. Scoring methodology

All of this is plain Python/pandas (`backend/scoring/`).
**The LLM never computes a score.** Same data + same weights → same result.

### 4.1 Raw metrics (`metrics.py`)

| Metric | Definition |
|---|---|
| `load_factor_pct` | passengers ÷ seats (2025) |
| `departures_per_runway` | departures ÷ open runways ≥5,000 ft |
| `vs_peak_pct` | 2025 passengers ÷ highest year 2014–2024 |
| `growth_vs_baseline_pct` | 2025 vs 2019 (pre-COVID). Skipped if 2019 had <100,000 passengers (new service – e.g. HVN would show +1,413%) |
| `growth_vs_last_year_pct` | 2025 vs 2024 |
| `avg_taxi_out_min`, `cancel_pct` | by departing airport (BTS On-Time) |
| `nas_delay_pct` | share of arriving flights delayed by the National Airspace System (BTS convention: by destination) |
| `passengers` | departing passengers, 2025 |
| `fare_premium_pct` | how much more expensive than comparable routes (Table 7) |

### 4.2 Percentiles
Each metric is turned into a **percentile among the 227 airports** (`rank(pct=True) × 100`).
This puts minutes, percents and flight counts on one 0–100 scale, and is robust to outliers
(ATL's size does not squash everyone else). Missing values stay missing.

### 4.3 The KPI: Expansion Opportunity Score (0–100)

| Component | Weight | Metrics (average of their percentiles) | Question it answers |
|---|---|---|---|
| Capacity pressure | 30 | load factor, departures per runway, vs peak | Is the airport already full? |
| Demand growth | 25 | growth vs 2019, growth vs 2024 | Is demand rising? |
| Congestion | 20 | taxi-out, NAS delay %, cancel % | Is it operationally strained? |
| Market scale | 15 | passengers | How big is the opportunity? |
| Pricing power | 10 | fare premium | Do travelers pay more to fly here? |

**Total score** = weighted average of the components. If a component is missing for an airport,
its weight is shared by the others (we divide by the weights that are available) instead of counting it as 0.

**Weights** are fixed defaults (pressure and growth matter most for an expansion case). The analyst can ask for
other weights ("give growth 50%"); the LLM passes them to `rank_airports` as numbers, the code recomputes,
and the weights used are always returned and shown.

### 4.4 Extra outputs on every airport
- **Airside vs Landside pressure** – the same percentiles split by *what* to build:
  airside (runways, airspace: departures per runway, taxi-out, NAS delay, cancellations) vs
  landside (terminal, passengers: load factor, vs peak, both growth metrics).
- **Confidence** – fixed rules: *Low* if ≥2 components are missing; *Medium* if one is missing or the airport has
  <1M passengers; else *High*. The reason is generated in code (`confidence_reason`) so the LLM cannot invent one.
- **Warnings** – missing components, cargo-dominated airports (≥50% cargo flights, e.g. ANC), new service vs 2019.

### 4.5 Question-specific metrics (`special.py`)
- **Long-haul share** – flights ≥3,000 miles (and ≥2,500 as an alternative), shown separately for passenger,
  cargo and all flights, because the answer depends on the definition (ANC: 2.8% of passenger flights vs 31.0% of all flights).
- **Unmet Demand Index** – average percentile of four signals: load factor, fare premium, NAS delay %, cancel %.
  Signals are returned strongest first – that is the "why".
- **Capacity gap** – seats needed to bring the load factor down to 80%: `passengers ÷ 0.80 − seats`.
  A lower estimate: people who did not fly at all are not in the data.

## 5. Where and how AI is used

| AI does | AI does not |
|---|---|
| Understand free-text questions, map names to codes ("LA" → LAX, mention BUR/LGB/ONT) and regions to states | Compute any score, rank, metric or difference ("how many more" → `compare_numbers`) |
| Choose the tool and its arguments (states, weights) | Choose weights unless the user asks |
| Explain results: what drives the score, what to invest in, caveats | Make up numbers (see the check below) |
| Add general background, **labeled** "General knowledge (not from our data)" | |
| Transcribe voice input (Gemini) | |

**Stack:** Google ADK (`Agent`, `Runner`, `DatabaseSessionService` in PostgreSQL) with `gemini-3.5-flash`.

**Guardrails**
1. **System prompt "iron rules"** (`backend/agent/instructions.md`): never invent or calculate numbers;
   say so when no tool can answer; write numbers exactly as tools return them.
2. **Automatic number check** (`backend/agent/verification.py`, two ADK callbacks): every number a tool returns
   is remembered; every number in the final answer must match one (1% tolerance; 0–10, numbers from the question and
   from the instructions are allowed, and so is the difference between two data numbers shown in the same answer,
   e.g. "0.5 points higher" for 8.7% vs 8.2%). Otherwise the numbers are written to the backend log (not shown in the chat, to keep answers clean).
   Deterministic code, not a second LLM.
3. **Deterministic explanations** – `confidence_reason`, warnings and `data_notes` come from the tools, and every
   metric is labeled with its component and side (airside/landside), so the LLM repeats facts instead of guessing them.
   Arithmetic goes through `compare_numbers`, which only accepts numbers that earlier tools returned.
4. **Answer shape by question type** – full structure (bottom line, numbers, why, assumptions & sources, confidence,
   follow-ups) for analysis questions; short natural replies for follow-ups, concepts, small talk and out-of-scope
   questions. Whenever numbers appear, their source and confidence must appear too.

## 6. Key tradeoffs

| Decision | Chosen | Alternative | Why |
|---|---|---|---|
| Scoring | Deterministic code, percentiles | Let the LLM judge | Reproducible, testable, explainable |
| Normalization | Percentiles | Min-max / z-scores | Robust to huge outliers (ATL, DFW); easy to explain ("higher than 90% of airports") |
| Weights | Fixed defaults, changeable on request | Ask the user first | Answers immediately; flexibility without an interview |
| Data | Live APIs where they exist + pre-processed files | All live, or all files | No API offers delays, long-haul or runways per airport |
| Agent framework | Google ADK | Hand-written loop, LangGraph | Tools, sessions and callbacks built in; small code |
| Number check | Code that matches numbers | A second "verifier" LLM | Deterministic, cheap, no new errors |
| Answer format | Prompt-guided structure | Enforced `output_schema` | ADK cannot combine tools with an output schema; conversation needs flexibility |
| Caching | None | Cache DOT API results | Simpler and always current; costs ~30 s per multi-tool answer |
| Users | One shared user, no login | Authentication | Demo scope; ADK already supports `user_id` |
| Frontend | Streamlit | React | Fast to build, Python only |

## 7. Assumptions and interpretations

| The exam says | We assumed |
|---|---|
| "most profitable" | Demand-vs-capacity pressure as a proxy – no cost or revenue data |
| "terminal expansion" | Rank by **landside** pressure, not only the total score |
| "LA" | LAX, and mention Burbank, Long Beach and Ontario |
| "New England" | CT, ME, MA, NH, RI, VT |
| "long haul" | ≥3,000 miles (≥2,500 shown too); share of **flights**, passenger and cargo separately |
| "unmet demand" | No direct measure exists → an index of four observable signals + a capacity gap |
| Data year | 2025 actual data (not projections), 2019 as the pre-COVID baseline |

## 8. Limitations and next steps

- **No forecasting, cost, land or regulatory data** – the agent says so.
- **Delay data covers large US airlines only**; three scored airports have none (their weight is redistributed).
- **Speed** – the DOT API is called on every tool call (~30 s per answer). Next: a 24-hour cache on the API client.
- **Gemini availability** – occasional 503 "high demand"; the UI shows a clear message. Next: automatic retry.
- **Single user** – conversations are shared per deployment. Next: login and a real `user_id`.
- **Next features** – stream tool calls live in the UI, spoken answers (text-to-speech), a scheduled refresh of the ETL files.
