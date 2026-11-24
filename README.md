# Ticket Triage Assistant

An AI-powered support triage application built with Python 3.11+, Pydantic, FastAPI, Vanilla HTML/CSS/JS, and a Typer CLI. It transforms raw customer support messages into validated, structured triage records with automated schema repair and offline prompt evaluation.

---

## Architecture

The codebase enforces strict separation of concerns across three layers:

1. **Triage Core (`app/core/`)**: Pure business logic with zero HTTP or UI coupling. Loads versioned Markdown prompts (`prompts/`), wraps the OpenAI SDK with `request_id` logging and exponential backoff retries, enforces strict Pydantic contracts (`LLMResponseSchema`, `TriageResult`), truncates messages exceeding 4,000 characters with a warning, and triggers a single self-repair pass (`repair.md`) if model output fails validation.
2. **REST API (`app/api/`, `app/main.py`)**: Thin async FastAPI routes under `/api/v1` (`POST /triage`, `GET /health`, `GET /options`), OpenAPI Swagger documentation at `/docs`, strict input bounds (`422` on empty or `>10,000` character messages), sanitized upstream error handling (`502`), and static file hosting for the web UI.
3. **Clients (`frontend/` & `app/cli.py`)**:
   - **Web Frontend**: Plain HTML/CSS/JS using `fetch`, character counter, loading/error states, priority badges, `Needs human review` indicator (`confidence < 0.5`), one-click reply copy, and 10-item `sessionStorage` history.
   - **Batch & Evaluation CLI**: `batch` processes folders of `.txt` files into CSV with fault isolation; `evaluate` benchmarks predictions against `labels.csv`.

---

## Quickstart (Fresh Clone)

### 1. Clone and create virtual environment

```bash
git clone <your-repo-url>
cd ticket-triage
python3 -m venv .venv
source .venv/bin/activate  # On Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY (and optional OPENAI_BASE_URL / MODEL_NAME, default: gpt-4o-mini)
```

### 3. Start the application (Single Command)

```bash
uvicorn app.main:app --reload
```

- **Web Interface**: `http://127.0.0.1:8000/`
- **Interactive Swagger Docs**: `http://127.0.0.1:8000/docs`

---

## CLI Batch Processing & Evaluation

Run triage across the 20 synthetic sample tickets (`samples/msg_01.txt` – `msg_20.txt`) and measure accuracy against ground truth:

```bash
python -m app.cli batch samples/ --out results.csv
python -m app.cli evaluate results.csv samples/labels.csv
```

---

## Prompt Iteration & Evaluation Results

Evaluated on the 20-message synthetic dataset (`samples/msg_01.txt` – `msg_20.txt`) at `temperature=0.1` (using `openai/gpt-oss-120b` via Groq OpenAI-compatible API, $0.00 USD):

| Prompt Version | Category Accuracy (Target >= 80%) | Priority Accuracy (Target >= 70%) | Key Changes |
| :--- | :---: | :---: | :--- |
| **v1 (Baseline)** | **90.0%** (18/20) | **75.0%** (15/20) | Initial zero-shot system prompt listing allowed enum values and JSON formatting constraints without operational priority definitions. |
| **v2 (Current)** | **95.0%** (19/20) | **85.0%** (17/20) | Added explicit Category & Priority Rubrics distinguishing `urgent` (outages/security breaches) from `high` (major blockers/duplicate charges) and `medium`/`low`, plus two few-shot examples in `classify.md`. |

---

## Quality Assurance & Testing

All unit and API tests run completely offline using an in-memory `FakeLLMClient`:

```bash
# Run offline test suite (24 tests: 14 core + 10 API)
pytest -v

# Run linter and formatting checks
ruff check .
ruff format --check .
```