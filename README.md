# Multiplayer Pong Prototype

This project provides a minimal multiplayer Pong experience with a FastAPI backend and a React (Vite) frontend. Two browser tabs can control individual paddles while a shared game state is maintained on the server.

## Prerequisites

- Python 3.10+
- Node.js 16+

## Running the backend

```bash
cd server
python -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\\Scripts\\activate`
pip install -r requirements.txt
uvicorn main:app --reload
```

The WebSocket endpoint is served at `ws://localhost:8000/ws`.

## Running the frontend

```bash
cd client
npm install
npm run dev
```

Open `http://localhost:5173` in two browser tabs. Each tab will be assigned to a different paddle automatically. Use `W`/`S`/`A`/`D` or the arrow keys to move your paddle.

Optional query parameters `?room=<id>&player=<1|2|auto>` can be added to the frontend URL to join different rooms or request a specific player slot.
