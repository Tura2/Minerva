# Minerva Backend

FastAPI-based trading research backend for Minerva copilot.

## Setup

### Prerequisites
- Python 3.9+
- pip and venv

### Installation

1. Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -e ".[dev]"  # Include dev dependencies
   ```

3. Configure environment:
   ```bash
   cp ../.env.example .env
   # Edit .env with your API keys and database URLs
   ```

### Running the Server

Development mode with auto-reload:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Production mode:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Testing

Run all tests:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=app
```

Run specific test:
```bash
pytest tests/test_validators.py::test_validate_price
```

### Linting and Formatting

Check code style:
```bash
ruff check .
```

Format code:
```bash
ruff format .
black .
```

## API Endpoints

### Health Check
- `GET /health` - Service health status

### Scanner
- `POST /scanner/scan` - Execute symbol screening
- `GET /scanner/candidates` - Get recent candidates

### Research
- `POST /research/execute` - Execute research workflow
- `GET /research/tickets/{ticket_id}` - Get ticket details
- `GET /research/tickets` - List all tickets

### Market Data
- `GET /market/history` - Fetch market OHLC history
- `GET /market/symbols/{market}` - Get valid symbols for market

## Architecture

```
app/
├── main.py              # FastAPI app initialization
├── config.py            # Environment and settings
├── routers/
│   ├── scanner.py       # Screening endpoints
│   ├── research.py      # Research workflow endpoints
│   └── market.py        # Market data endpoints
├── services/
│   ├── workflow.py      # LangGraph workflow engine
│   ├── scanner.py       # Screening logic
│   └── openrouter_client.py  # LLM integration
├── models/
│   └── schemas.py       # Pydantic schemas
└── utils/
    └── validators.py    # Validation functions
```

## Key Features

- **yfinance Integration**: Fetch OHLC and volume data
- **LangGraph Orchestration**: Deterministic workflow execution
- **OpenRouter API**: LLM research integration with retry policy
- **Market Support**: US (S&P 500, Nasdaq) and TASE
- **Structured Output**: JSON schema validation for research tickets
