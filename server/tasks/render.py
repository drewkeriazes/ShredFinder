"""Background task: render a project timeline into a final video."""

import json
import logging
import traceback

import server.models  # noqa: F401 — register all models so relationships resolve
from server.models.base import async_session_factory
from server.services.renderer import render_timeline

logger = logging.getLogger(__name__)

# In-memory render job tracking (would be Redis/DB in production)
render_jobs: dict[str, dict] = {}


async def render_project_task(project_id: str, job_id: str, ws_manager=None) -> None:
    """Background task: render the full timeline for a project.

    Args:
        project_id: UUID of the Project to render.
        job_id: Unique job ID for tracking progress.
        ws_manager: Optional WebSocketManager for progress broadcasts.
    """
    render_jobs[job_id] = {
        "status": "rendering",
        "percent": 0.0,
        "project_id": project_id,
        "output_path": None,
        "error": None,
    }

    async with async_session_factory() as session:
        async def _progress(percent: float):
            render_jobs[job_id]["percent"] = round(percent, 1)
            if ws_manager:
                await ws_manager.broadcast(json.dumps({
                    "type": "render_progress",
                    "job_id": job_id,
                    "project_id": project_id,
                    "percent": round(percent, 1),
                }))

        try:
            output_path = await render_timeline(
                project_id, job_id, session, progress_callback=_progress
            )

            if output_path:
                render_jobs[job_id]["status"] = "complete"
                render_jobs[job_id]["percent"] = 100.0
                render_jobs[job_id]["output_path"] = str(output_path)

                if ws_manager:
                    await ws_manager.broadcast(json.dumps({
                        "type": "render_complete",
                        "job_id": job_id,
                        "project_id": project_id,
                    }))
            else:
                render_jobs[job_id]["status"] = "error"
                render_jobs[job_id]["error"] = "Render returned no output"

                if ws_manager:
                    await ws_manager.broadcast(json.dumps({
                        "type": "render_error",
                        "job_id": job_id,
                        "error": "Render returned no output",
                    }))

        except Exception as e:
            logger.error("Render task failed for job %s: %s\n%s",
                         job_id, e, traceback.format_exc())
            render_jobs[job_id]["status"] = "error"
            render_jobs[job_id]["error"] = str(e)

            if ws_manager:
                await ws_manager.broadcast(json.dumps({
                    "type": "render_error",
                    "job_id": job_id,
                    "error": str(e),
                }))
