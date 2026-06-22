# Agnes AI Platform

![Python](https://img.shields.io/badge/python-3776AB?logo=python&logoColor=white) ![Vue](https://img.shields.io/badge/vue-4FC08D?logo=vuedotjs&logoColor=white) ![License](https://img.shields.io/badge/license-Apache%202.0%20%2B%20Commons%20Clause-red)

**🌐 Language / 语言**

[**English** ](README.md) | [中文](README_zh.md)

**An all-in-one AI creation platform — chat with AI, generate images & videos, and compose on an infinite canvas.** Powered by Agnes AI, with a Vue 3 + FastAPI full-stack architecture that keeps your API key secure on the server.

## What Is Agnes AI Platform

Agnes AI Platform is a self-hosted web application that brings together multiple AI capabilities into a single, cohesive experience:

- **AI Chat** — Conversational AI with tool calling. Chat naturally, and the AI can automatically trigger image or video generation when it detects your intent.
- **Image Generation** — Text-to-image and image-to-image, with multiple models and size options.
- **Video Generation** — Text-to-video, image-to-video, and keyframe animation, with async polling and real-time progress.
- **Infinite Canvas** — A free-form workspace where you can place generated images as nodes, connect them, and re-generate or remix with context-aware operations.
- **Multi-Provider Management** — Add and switch between multiple AI API providers (different base URLs, API keys) from the settings page. No need to edit `.env` files after initial setup.
- **Generation History** — Persistent history with thumbnails, GIF previews, filtering, and batch operations.

All API keys are encrypted and stored on the server — they never reach the browser.

## How We Got Here

Agnes AI Platform started as a simple image & video generation tool. Here's how it evolved:

| Phase | What Changed |
|---|---|
| **v1 — Generator** | Text-to-image, image-to-image, text-to-video, image-to-video. A clean tool with async polling and history. |
| **v2 — Multi-Provider** | Replaced the single `.env` API key with a database-backed provider system. Add, edit, and switch providers from the UI. API keys encrypted at rest. |
| **v3 — AI Chat** | Added a conversational AI interface with tool calling. The AI can detect your intent and trigger image/video generation automatically. Full SSE streaming. |
| **v4 — Infinite Canvas** | Introduced a free-form canvas for composing and remixing generated images. Nodes, connections, mask editing, and context-aware re-generation. |

The platform continues to grow, but the core principle remains the same: **a self-hosted, secure, all-in-one AI creation workspace.**

## Quick Start

### Prerequisites

| Tool | Version | Why |
|---|---|---|
| **Python** | 3.10+ (3.11+ recommended) | Backend runtime |
| **Node.js** | 18+ (20+ LTS recommended) | Frontend build |

### 1. One-Click Start

Open a terminal in the project root and run:

```bash
# macOS / Linux
./start.sh

# Windows
start.bat

# Or use the Python launcher (cross-platform)
python start.py
```

This automatically starts both the backend and frontend in one command. On first run it will prompt you to configure your API key.

### 2. Manual Start

#### Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate      # macOS / Linux
# Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — at minimum, set AGNES_API_KEY for the initial default provider.
# After first launch, you can manage providers from the frontend settings page.
```

Start the backend (macOS/Linux):

```bash
./start.sh
```

Start the backend (Windows):

```batch
start.bat
```

Or manually:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Verify: http://localhost:8000/health or http://localhost:8000/docs

#### Frontend

Open a **new terminal**:

```bash
cd frontend

# Install dependencies
npm install

# Start dev server (port 5173, auto-proxies /api → backend:8000)
npm run dev
```

Visit http://localhost:5173 — you're ready to go.

### 3. First-Time Setup

1. Open the **Settings** page (`/settings`).
2. Your `.env` API key is automatically loaded as the default provider.
3. Add more providers if needed — each with its own base URL and API key.
4. Start creating — chat, generate images/videos, or open the canvas.

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Vue 3 (Composition API) + Vite + TypeScript + Vue Router + Pinia + Element Plus |
| Backend | Python 3.10+ · FastAPI · SQLAlchemy 2.0 (async) · httpx (async HTTP client) |
| Database | SQLite (default, zero-config) / PostgreSQL (optional) |
| AI Provider | Agnes AI API (OpenAI-compatible) |

## FAQ

**Q: Why a BFF layer instead of calling the AI API directly from the browser?**

A: Two reasons — (1) your API key stays on the server and never reaches the browser, (2) the server handles async task polling, history persistence, and media processing that a pure frontend can't do reliably.

**Q: How long does video generation take?**

A: Usually 2–6 minutes. The platform polls in the background — you can navigate away and check back later.

**Q: Can I use other OpenAI-compatible APIs?**

A: Yes. Add a new provider in Settings with your custom base URL and API key. The platform supports any OpenAI-compatible chat, image, and video endpoints.

**Q: Can I deploy this to production?**

A: Yes. Build the frontend (`npm run build`) and serve it statically. Deploy the backend with any ASGI host. Set `FRONTEND_ORIGINS` and `DATABASE_URL` for your production environment.

## License

Apache License 2.0 with Commons Clause — source code is open and free to use for personal, educational, and research purposes. **Commercial use is prohibited.** See [LICENSE](LICENSE) for details.
