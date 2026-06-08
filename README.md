# Customer Agent 3

Customer Agent 3 is a customer-service demo project split into two main flows:
- `qa`: classify -> retrieve -> answer
- `action`: classify -> LangChain agent -> business tools

The repository keeps a structure similar to `客服agent2`, but replaces the LangGraph workflow with a lighter service orchestration layer.

## Project Structure

```text
.
|- backend/              app, flows, routers, tools, memory, stores
|- frontend/             Streamlit demo page
|- data/                 Sample knowledge base files
|- logs/                 Runtime logs
|- Dockerfile            Docker image build file
|- docker-compose.yml    Docker Compose file
|- requirements.txt
|- .env.example
```

## Main Flow

1. FastAPI receives the user query.
2. A routing layer decides whether the request goes to `qa` or `action`.
3. `qa` path:
   - retrieve knowledge-base context
   - generate an answer from retrieved context
4. `action` path:
   - run a constrained `create_agent(...)`
   - let the agent call deterministic customer-service tools
   - return the final execution result

## Local Run

1. Copy `.env.example` to `.env`
2. Fill in `DASHSCOPE_API_KEY`
3. Start the API:

```bash
uvicorn backend.app.api_server:app --reload
```

4. Optionally start the Streamlit demo:

```bash
streamlit run frontend/app.py
```

## Docker Run

1. Prepare `.env`
2. Start all services:

```bash
docker compose up --build
```

After startup:
- API: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:8501`

On first startup, the `api` service will initialize the knowledge base automatically when the pgvector table is still empty.
