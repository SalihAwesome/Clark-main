# Running Clark

There are two ways to run Clark:

- **Docker** (recommended) — builds and runs everything in containers, minimal setup
- **Local** — run the Python backend and Node.js frontend directly on your machine

Both need a **Google Gemini API key**.

---

## 0. Get an API key

1. Go to https://aistudio.google.com/ and get a Gemini API key.
2. Copy `backend/.env.example` to `backend/.env`:
   ```bash
   cd backend
   cp .env.example .env
   ```
3. Open `backend/.env` and set your key:
   ```
   GEMINI_API_KEY=paste_your_key_here
   ```

---

## 1. Run with Docker (recommended)

**Prerequisites:** Docker and Docker Compose installed.

```bash
# From the project root
docker compose up --build
```

- **Frontend:** http://localhost:3000
- **Backend:** http://localhost:8008

The browser runs headlessly inside the container. Your profile, credentials, and conversation history persist in a Docker volume.

**Useful commands:**

| Command | What it does |
|---|---|
| `docker compose up --build` | Build images and start services |
| `docker compose up` | Start services (reuse existing images) |
| `docker compose down` | Stop services (data preserved) |
| `docker compose down -v` | Stop services and **delete stored data** |
| `docker compose logs -f` | Follow live logs from both services |
| `docker compose logs backend` | Logs from the backend only |
| `docker compose logs frontend` | Logs from the frontend only |
| `docker compose restart` | Restart both services |

**Overriding backend settings:**

```bash
# Example: pass a custom env var without editing .env
BROWSER_LOCALE=en-GB docker compose up
```

---

## 2. Run locally

**Prerequisites:** Python 3.12–3.14, Node.js, npm, Google Chrome installed.

### 2a. Backend (port 8008)

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

# Install dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt

# Install the browser engine (one-time)
python -m playwright install chromium

# Start the API server
python -m uvicorn main:app --reload --port 8008
```

You should see: `Uvicorn running on http://localhost:8008`

### 2b. Frontend (port 3000)

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

You should see: `Ready on http://localhost:3000`

---

## 3. Windows one-click launcher

Double-click `START.bat` in the project root. On first run it creates `backend/.env` and opens it so you can paste your API key. Run `START.bat` again to start both services.

---

## 4. Configuration reference

All settings live in `backend/.env`. Key ones:

| Variable | Default | Note |
|---|---|---|
| `GEMINI_API_KEY` | — | **Required.** Your Google AI Studio key |
| `FIREWORKS_API_KEY` | — | Optional fallback provider |
| `BROWSER_HEADLESS` | `false` | `true` in Docker; `false` shows the browser window locally |
| `BROWSER_LOCALE` | `en-US` | Browser UI language |
| `BROWSER_PERSISTENT` | `true` | Reuse a saved Chrome profile across runs |
| `LLM_TIMEOUT` | `75` | Per-call timeout in seconds |

---

## 5. Troubleshooting

| Problem | Likely fix |
|---|---|
| `GEMINI_API_KEY` not set | Create `backend/.env` from `.env.example` and add your key |
| Docker: Playwright fails | Ensure your Docker version supports the Playwright base image (Docker 24+ recommended) |
| Docker: port conflict | Change ports in `docker-compose.yml` under the `ports:` section |
| Local: "chromium not found" | Run `python -m playwright install chromium` inside your venv |
| Local: Next.js can't reach backend | Ensure the backend is running on port 8008 before starting the frontend |
| Local: port 3000 in use | Kill the old process or change the port: `npm run dev -- -p 3001` |
| Blank page in browser | Check both terminals for errors; the frontend `.env` rewrites API calls to the backend |
