# HalloDOC Backend

HalloDOC is a FastAPI backend for a German medical triage and patient chat assistant. It combines authenticated patient sessions, physician/practice management, local conversation storage, ChromaDB-based retrieval, and Ollama-powered generation.

The project is designed to run locally for development and with Docker Compose on a VPS for production.

## Features

- FastAPI REST API
- Patient and physician authentication with HTTP-only JWT cookies
- Practice-based patient registration
- AI chat sessions with saved conversation history
- Medical RAG pipeline using ChromaDB
- PDF ingestion for medical guideline documents
- Ollama integration for chat and embeddings
- PostgreSQL production database
- Dockerized production deployment

## Tech Stack

- Python 3.12
- FastAPI
- SQLAlchemy
- PostgreSQL in production
- SQLite fallback for local development
- ChromaDB
- Ollama
- Uvicorn
- Docker Compose

## Project Structure

```text
app/
  auth/          Authentication routes, JWT helpers, user registration/login
  chat/          Protected chat endpoints and chat orchestration
  core/          Application configuration
  ingestion/     PDF chunking, embedding, and ChromaDB ingestion
  models/        SQLAlchemy models, database setup, seed script
  prompts/       System prompt used by the assistant
  services/      RAG-related service code
Dockerfile
docker-compose.yml
requirements.txt
```

## Requirements

For local development:

- Python 3.12
- Ollama running locally
- ChromaDB running locally or through Docker

For production/VPS deployment:

- Docker
- Docker Compose
- Ollama available on the VPS host or reachable from the backend container

Required Ollama models:

```bash
ollama pull nomic-embed-text
ollama pull hallodoc:latest
```

If `hallodoc:latest` is a custom model, create or import it before starting the backend.

## Environment Variables

Create a `.env` file in the project root.

```env
JWT_SECRET=replace-with-a-long-random-secret
POSTGRES_PASSWORD=replace-with-a-long-random-password

OLLAMA_MODEL=hallodoc:latest
OLLAMA_DOCKER_BASE_URL=http://host.docker.internal:11434

BACKEND_PORT=8000
POSTGRES_VERSION=16-alpine
CHROMA_VERSION=1.5.9

PRACTICE_CODE=123456
COOKIE_SECURE=true
COOKIE_SAMESITE=lax
```

For production, do not keep default secrets. Use long random values for `JWT_SECRET` and `POSTGRES_PASSWORD`.

## Production Deployment

The production compose stack includes:

- `backend`: FastAPI application
- `postgres`: PostgreSQL database
- `chromadb`: private ChromaDB vector database

Start the application:

```bash
mkdir -p data/chroma_db data/medicines
docker compose up -d --build
```

Check service status:

```bash
docker compose ps
docker compose logs -f backend
```

The API will be available on:

```text
http://YOUR_SERVER_IP:8000
```

For a real production deployment, put a reverse proxy such as Nginx, Caddy, or Traefik in front of the backend and enable HTTPS.

## Ollama in Production

By default, the backend container connects to Ollama on the VPS host:

```env
OLLAMA_DOCKER_BASE_URL=http://host.docker.internal:11434
```

Make sure Ollama is running on the VPS and is reachable from Docker.

If Ollama runs on another server, set:

```env
OLLAMA_DOCKER_BASE_URL=http://YOUR_OLLAMA_HOST:11434
```

## Database

Production uses PostgreSQL through Docker Compose:

```text
postgresql+psycopg2://hallodoc:<POSTGRES_PASSWORD>@postgres:5432/hallodoc
```

Database tables are created automatically when the FastAPI app starts.

The PostgreSQL data is stored in the Docker volume:

```text
postgres_data
```

## Seed Test Data

To create a test practice, physician, and patient:

```bash
docker compose exec backend python -m app.models.seed
```

Default seed values:

```text
Practice code: 123456
Physician: arzt@hallodoc.de / Test1234!
Patient: patient@hallodoc.de / Test1234!
```

Change these before using the system with real users.

## Medical Document Ingestion

Place PDF files in:

```text
data/medicines/
```

Run ingestion:

```bash
docker compose exec backend python -m app.ingestion.ingest
```

Show ChromaDB collection stats:

```bash
docker compose exec backend python -m app.ingestion.ingest --stats
```

The ingestion pipeline:

1. Reads PDFs from `data/medicines`
2. Splits text into medical chunks
3. Embeds chunks with Ollama using `nomic-embed-text`
4. Stores vectors in ChromaDB

## Local Development

Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install psycopg2-binary==2.9.10
```

Run the app locally:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

By default, local development uses:

```text
SQLite: ./data/hallodoc.db
ChromaDB: localhost:8000
Ollama: http://localhost:11434
```

You can override these values in `.env`.

## API Overview

Interactive API docs are available at:

```text
http://localhost:8000/docs
```

Main endpoints:

```text
POST /auth/patient/register
POST /auth/patient/login
POST /auth/physician/register
POST /auth/physician/login
POST /auth/refresh
POST /auth/logout

POST /chat/message
POST /chat/message/stream
GET  /chat/sessions
GET  /chat/session/{session_id}/messages
POST /chat/session/{session_id}/close
```

Chat endpoints require a valid patient session cookie.

## Example Patient Login

```bash
curl -i -X POST http://localhost:8000/auth/patient/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "patient@hallodoc.de",
    "password": "Test1234!"
  }'
```

The backend returns authentication cookies. Use those cookies when calling protected chat endpoints.

## VPS Notes

- Keep `chromadb` and `postgres` private; the compose file does not expose them publicly.
- Expose the backend through HTTPS in a reverse proxy.
- Set `COOKIE_SECURE=true` when using HTTPS.
- Use strong secrets in `.env`.
- Back up the `postgres_data` volume and `data/chroma_db`.
- Do not use the seeded test users in production.

## Medical Disclaimer

HalloDOC is a software assistant and does not replace professional medical diagnosis, emergency care, or treatment. Any production use should include clinical review, safety testing, and appropriate legal/compliance checks for the target jurisdiction.

