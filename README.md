# Veo3-gen — Automated Video Generation with Google Flow

A full-stack web application that automates video generation using **Google Flow (Veo 3)** via browser automation. Upload images, assign prompts, and receive generated videos organized in Google Drive — all through a clean web UI.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────────┐
│  React Frontend │────▶│  Node/Express Backend │────▶│  Flask VM Worker        │
│  (Vite)         │     │  + MySQL              │     │  (Playwright + Chrome)  │
│  :5173 / dist   │     │  :3000                │     │  :8000                  │
└─────────────────┘     └──────────────────────┘     └─────────────────────────┘
                                                                │
                                                                ▼
                                                       Google Flow (Veo 3)
                                                       labs.google/fx/tools/flow
                                                                │
                                                                ▼
                                                       Google Drive (G:\)
```

**Frontend** — React + Vite SPA served by the backend in production. Handles image uploads, per-image prompt assignment (via UI or Excel/CSV), job status polling, and Drive links.

**Backend** — Node.js/Express REST API with MySQL. Manages users, JWT sessions, and job records. Proxies image uploads to the VM worker.

**VM Worker** — Flask API running on a local Windows machine with Chrome and a logged-in Google account. Uses Playwright to automate Google Flow, generate videos, and upload results to Google Drive via the local `G:\` mount.

---

## Features

- Upload multiple images (JPG, PNG, WEBP) and assign individual prompts per image
- Load prompts in bulk from Excel or CSV (supports multiple prompts per image via `_p2`, `_p3` naming)
- 3 parallel browser workers for faster processing
- Videos automatically organized in Google Drive — one subfolder per image
- Public shareable Drive link delivered to the frontend when the job completes
- Auto-cleanup of old Drive folders after 2 hours
- JWT authentication with session revocation
- Job cancellation support
- Progress tracking in real time

---

## Requirements

### Backend & Frontend
- Node.js >= 18
- MySQL 8 (or Docker)
- Docker (optional, for containerized deployment)

### VM Worker (Windows only)
- Python 3.10+
- Google Chrome installed
- A Google account logged in and with access to [Google Flow](https://labs.google/fx/tools/flow)
- Google Drive desktop app mounted as `G:\`
- A Google Cloud service account with Drive API enabled (for folder permissions)
- `google_flow_bot_paralelo.py` automation script (not included — proprietary)

---

## Setup

### 1. Clone

```bash
git clone https://github.com/automationventamon/Veo3-gen.git
cd Veo3-gen
```

### 2. Environment variables

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

```env
PORT=3000
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=flowgen
MYSQL_USER=flowgen
MYSQL_PASSWORD=your_password
JWT_SECRET=your_jwt_secret
JWT_EXPIRES_IN=8h
VM_WORKER_URL=http://<vm-worker-ip>:8000
CLIENT_URL=*
```

### 3. Database

Run the schema on your MySQL instance:

```bash
mysql -u root -p < backend/docker/mysql/init/01_schema.sql
```

Or use Docker Compose (see below).

### 4. Backend

```bash
cd backend
npm install
npm start
```

### 5. Frontend (development)

```bash
cd frontend
npm install
npm run dev
```

For production, build the frontend first — the backend serves `frontend/dist` as static files:

```bash
cd frontend && npm run build
cd ../backend && npm start
```

### 6. Docker (backend + MySQL)

```bash
docker build -t veo3-gen .
docker run -p 3000:3000 --env-file .env veo3-gen
```

---

## VM Worker Setup (Windows)

The VM worker is a Flask app that drives Chrome via Playwright to automate Google Flow video generation.

### Install dependencies

```bash
cd vm-worker
pip install flask playwright google-auth google-api-python-client
playwright install chrome
```

### Configure paths in `app.py`

Edit these constants at the top of `app.py` to match your machine:

| Constant | Description |
|----------|-------------|
| `_DRIVE_CREDS_FILE` | Path to your Google service account JSON key |
| `_DRIVE_PARENT_ID` | Google Drive folder ID where videos are stored |
| `_DRIVE_LOCAL_ROOT` | Local path to your Google Drive mount (e.g. `G:\My Drive\Flow\Videos`) |
| `gbot.SESSION_DIR` | Chrome profile directory for Playwright |

### Google Drive setup

1. Enable the **Google Drive API** in [Google Cloud Console](https://console.cloud.google.com/)
2. Create a **Service Account** and download the JSON key
3. Share your target Drive folder with the service account email (Editor access)
4. Mount Google Drive desktop app so files sync via the local filesystem (`G:\`)

> The worker copies videos to `G:\` directly (avoiding service account quota limits) and only uses the API to make the folder public and retrieve its ID.

### Start the worker

```bash
cd vm-worker
python app.py
# or double-click start_worker.bat (appends to worker.log)
```

On first run, Chrome will open and may require you to log in to your Google account. After login the session is persisted in `flow_session_chrome/`.

---

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/login` | — | Login, returns JWT token |
| `POST` | `/api/logout` | ✓ | Revoke session |
| `POST` | `/api/jobs` | ✓ | Create job (multipart: `images[]`, `prompts` JSON) |
| `GET` | `/api/jobs` | ✓ | List all jobs for current user |
| `GET` | `/api/jobs/:id` | ✓ | Get job status + Drive link |
| `POST` | `/api/jobs/:id/cancel` | ✓ | Cancel a running job |
| `GET` | `/api/health` | — | Health check |

### VM Worker endpoints (internal)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/job` | Submit job to worker |
| `GET` | `/api/job/:id` | Poll job status |
| `POST` | `/api/job/:id/cancel` | Cancel job |
| `GET` | `/api/health` | Worker health + queue size |

---

## Multi-prompt via Excel/CSV

You can assign multiple prompts to the same image using a spreadsheet:

| filename | prompt |
|----------|--------|
| photo.jpg | A cinematic sunset transition |
| photo.jpg | A slow zoom into the horizon |
| other.jpg | A dynamic action scene |

The frontend renames duplicate images as `photo_p2.jpg`, `photo_p3.jpg`, etc. before submission. In Drive, each gets its own subfolder.

---

## Project Structure

```
Veo3-gen/
├── frontend/               # React + Vite SPA
│   └── src/
│       ├── components/
│       │   ├── ImageUploader.jsx   # Upload + Excel prompt loader
│       │   └── JobStatus.jsx       # Progress + Drive link
│       └── pages/
│           └── VideoGeneratorPage.jsx
├── backend/                # Node.js / Express API
│   ├── server.js
│   ├── docker/
│   │   ├── seed-users.js
│   │   └── mysql/init/01_schema.sql
│   └── package.json
├── vm-worker/              # Flask worker (Windows)
│   ├── app.py              # Main Flask app + Playwright adapter
│   └── start_worker.bat    # Launch script (appends logs)
├── Dockerfile              # Multi-stage build (frontend + backend)
├── .env.example
└── .gitignore
```

---

## Notes

- The VM worker must run on a Windows machine with a real Google account — Google Flow requires an authenticated browser session.
- Google Flow (Veo 3) generates up to 4 video variants per prompt. Some may fail depending on content policy or rate limits.
- Drive folders are auto-deleted after 2 hours via the cleanup thread.
- Worker logs are written to `vm-worker/worker.log` (append mode when using `start_worker.bat`).
