# Dietly

Project developed by Tommaso Carlotti

Dietly is a local-first AI nutrition planner built with Python, JavaScript, Docker, MySQL, and Ollama.
It helps users track meals, estimate macros from photos or manual ingredients, manage daily routine targets, and receive AI guidance.

## Important License Notice

This project is released under a **non-commercial license**.

- Personal, study, and research use: allowed.
- Any commercial use: **not allowed without written permission**.
- Commercial licensing contact: **tequilastudios@gmail.com**

Read full terms in [`license.txt`](license.txt).

## Main Features

- Multi-user registration and login (JWT auth)
- Meal tracking (create, edit, delete)
- AI image analysis for meals (Ollama vision model)
- Manual ingredient builder with auto macro estimation
- Daily routine targets (kcal, proteins, carbs, fats)
- Smart AI routine optimization (optional)
- Daily summary + AI suggestions
- Daily timeline + needs estimation + hydration tracking
- DietlyBot chat:
  - multiple chat sessions
  - new chat creation
  - typing indicator
  - voice input (browser support required)
  - improved message formatting
- Body photo analysis and progress comparison

## Tech Stack

- Backend: FastAPI (Python 3.11)
- Frontend: HTML/CSS/Vanilla JavaScript
- Database: MySQL 8.4
- AI Runtime: Ollama (local)
- Containers: Docker Compose

## Quick Start (Mac)

### 1) Prerequisites

- Docker Desktop installed and running
- Ollama installed and running
- Git installed

Check:

```bash
docker --version
docker compose version
ollama --version
git --version
```

### 2) Clone the repository

```bash
git clone <YOUR_GITHUB_REPO_URL>.git
cd Diety
```

### 3) Pull recommended Ollama models

```bash
ollama pull llava:latest
ollama pull mistral:latest
```

### 4) Start the app

```bash
docker compose up --build
```

### 5) Open in browser

- App: http://localhost:8000
- Health check: http://localhost:8000/health

## Useful Commands

Stop services:

```bash
docker compose down
```

Full reset (including database volume):

```bash
docker compose down -v
```

Restart backend only:

```bash
docker compose restart backend
```

Backend logs:

```bash
docker compose logs -f backend
```

## Configuration Notes

Default service wiring is in [`docker-compose.yml`](docker-compose.yml):

- Backend exposed on port `8000`
- MySQL kept internal (not exposed to host by default)
- Ollama URL used by backend: `http://host.docker.internal:11434`

If you want to change models or AI behavior at runtime, use the in-app `/settings` page.

## Project Structure

```text
Diety/
  backend/
    app/              # FastAPI app, routers, models, services, AI client
    static/           # Frontend assets (HTML/CSS/JS, logo)
    Dockerfile
    requirements.txt
  docker-compose.yml
  guide.txt
  gitinstruction.txt
  heritage.txt
  license.txt
```

## Security Checklist Before Publishing

- Do not commit personal credentials or tokens
- Do not commit private user photos/datasets
- Rotate any default secrets before production use

## Attribution

Keep this notice in redistributions and derivative works:

`Project developed by Tommaso Carlotti`
