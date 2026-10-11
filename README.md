# NL-to-SQL Data Analyst Agent

An agentic AI system that answers natural language questions over a PostgreSQL database by autonomously retrieving relevant schema context, inspecting tables, generating SQL, validating it, and executing it — built from scratch on top of LangChain/LangGraph's agent framework rather than a prebuilt SQL toolkit, and exposed as a REST API via FastAPI.

## What it does

You send a question in plain English (e.g. *"Which country had the highest total confirmed cases as of the most recent date?"*), and the agent:

1. Retrieves relevant table/column descriptions from a vector store (Chroma) to narrow down what's relevant to the question
2. Lists available tables in the database and inspects their schema/sample rows
3. Generates a PostgreSQL query to answer the question
4. Double-checks the query for common SQL mistakes before running it
5. Executes the query and returns a plain-language answer

The agent decides which of these steps to take and in what order — it isn't a fixed pipeline, it's tool-calling driven by the LLM's own reasoning. Conversation state is maintained per session, so follow-up questions can reference prior context.

## Why I built it this way

Most SQL agent tutorials use LangChain's prebuilt `create_sql_agent` helper. I built the underlying tools manually (`retrieve_relevant_schema`, `sql_db_list_tables`, `sql_db_schema`, `sql_db_query`, `sql_db_query_checker`) to understand exactly what an agent needs to reliably reason over an unfamiliar database — semantic schema retrieval, discovery, self-verification before execution, and safe read-only access (no DML statements permitted).

## Tech stack

- **Orchestration:** LangChain (`create_agent`) + LangGraph (`InMemorySaver` for per-session conversation state)
- **Retrieval:** Chroma (vector DB) — stores table/column-level schema descriptions, retrieved semantically before SQL generation to guide table selection
- **LLM:** Configurable via `init_chat_model` — built and tested against Google Gemini (`gemini-3.1-flash-lite`), also supports Anthropic Claude and Groq
- **API:** FastAPI, with a `/ask` endpoint and session-based conversation memory
- **Database:** PostgreSQL, accessed via `psycopg`
- **Dataset:** COVID-19 daily case data (~300K rows, sourced from Kaggle) — country/province-level confirmed, death, and recovered case counts over time
- **Env management:** `uv` (`pyproject.toml` / `uv.lock`)

## Setup

**1. Clone and install dependencies**
```bash
git clone <your-repo-url>
cd nl-to-sql-agent
uv sync
```

**2. Set up PostgreSQL**

Create a local database:
```sql
CREATE DATABASE covid_db;
```

**3. Configure environment variables**

Copy `.env.example` to `.env` and fill in your values:
```
DB_NAME=covid_db
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
GOOGLE_API_KEY=your_gemini_key
```

**4. Load the data**
```bash
uv run inject.py
```
This reads `data/covid_19_data.csv`, cleans column names, and loads it into the `covid_data` table in PostgreSQL.

**5. Build the schema vector index**
```bash
uv run schema_store.py
```
This embeds table/column descriptions into a local Chroma store (`chroma_db/`) for the agent's retrieval step.

**6. Run the API**
```bash
uv run uvicorn main:app --reload
```
Visit `http://127.0.0.1:8000/docs` for an interactive Swagger UI to test the `/ask` endpoint directly.

## Example

**Request**
```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Which country had the highest total confirmed cases as of the most recent date?"}'
```

**Response**
```json
{
  "answer": "As of the most recent date in the data, the US had the highest total confirmed cases, followed by India and Brazil.",
  "session_id": "b3f1a2c4-..."
}
```
Pass the returned `session_id` back on follow-up requests to preserve conversation context.

## Known limitations

- **Cumulative data trap** — the dataset stores a daily *running total* per region rather than daily new cases. A naive `SUM(confirmed)` across all rows massively overcounts, since it adds up the same cumulative figure repeatedly across hundreds of days instead of taking the latest value per country. The agent needs a clearly scoped question (e.g. "as of the most recent date") to avoid this — otherwise it can return inflated, misleading numbers.
- **Connection-per-call** — each tool call opens and closes its own database connection rather than using a connection pool. Fine for a demo at this scale, but connection pooling (e.g. via `psycopg_pool`) would be the next step for production use.
- **Single-table schema store** — the Chroma index currently holds one table's description. The retrieval step is architecturally in place for scaling to a multi-table database, but hasn't been tested against one yet.
- **Gemini free-tier rate limits** — the `gemini-3.1-flash-lite` free tier has daily/per-minute request caps; heavy testing can hit `RESOURCE_EXHAUSTED` errors. The model is swappable via `init_chat_model` without touching agent logic.

## Possible improvements

- Add automated tests against a fixed set of sample questions with expected SQL shapes
- Add connection pooling for the database layer
- Expand the Chroma schema store to a multi-table database to properly exercise the retrieval step
- Deploy the API (e.g. Docker + a cloud host) for a live public demo link