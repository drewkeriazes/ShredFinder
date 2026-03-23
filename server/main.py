"""ShredFinder Web Video Editor — FastAPI application entry point.

Run with:
    shredfinder-server          (via pyproject.toml script entry)
    uvicorn server.main:app     (directly)
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.config import settings
from server.models.base import init_db
import server.models  # noqa: F401 — register all ORM models for relationship resolution

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class WebSocketManager:
    """Manages active WebSocket connections and broadcasts messages to all."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket connected (%d total)", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("WebSocket disconnected (%d total)", len(self.active_connections))

    async def broadcast(self, message: str) -> None:
        """Send a message to all connected clients. Removes stale connections."""
        stale = []
        for conn in self.active_connections:
            try:
                await conn.send_text(message)
            except Exception:
                stale.append(conn)
        for conn in stale:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, message: str) -> None:
        """Send a message to a single connected client."""
        try:
            await websocket.send_text(message)
        except Exception:
            self.disconnect(websocket)


# ---------------------------------------------------------------------------
# Application lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown."""
    # --- Startup ---
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.info("Starting %s", settings.APP_NAME)
    settings.ensure_dirs()
    await init_db()
    logger.info("Database initialized")

    yield

    # --- Shutdown ---
    logger.info("Shutting down %s", settings.APP_NAME)


# ---------------------------------------------------------------------------
# Create the FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ShredFinder API",
    description="Backend for the ShredFinder Web Video Editor",
    version="0.1.0",
    lifespan=lifespan,
)

# Attach the WebSocket manager to app state so routes can access it
app.state.ws_manager = WebSocketManager()

# CORS — allow all origins in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file serving for uploaded media (thumbnails, proxies, etc.)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(settings.DATA_DIR)), name="static")


# ---------------------------------------------------------------------------
# Include API routers
# ---------------------------------------------------------------------------

from server.api.auth import router as auth_router
from server.api.projects import router as projects_router
from server.api.media import router as media_router
from server.api.detection import router as detection_router
from server.api.render import router as render_router

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(media_router)
app.include_router(detection_router)
app.include_router(render_router)


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time progress updates.

    Clients connect here to receive broadcast messages about:
    - Proxy generation progress
    - Detection progress
    - Render progress
    """
    manager: WebSocketManager = app.state.ws_manager
    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; clients can also send messages
            data = await websocket.receive_text()
            # Echo back as acknowledgment (clients can send ping/commands)
            await manager.send_personal(websocket, json.dumps({"type": "ack", "data": data}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """Simple health check endpoint."""
    return {"status": "ok", "app": settings.APP_NAME}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run():
    """Entry point for the `shredfinder-server` console script."""
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    run()
