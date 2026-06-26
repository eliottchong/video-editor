"""FastAPI server for the video editor UI."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import video_editor_mod

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
UPLOAD_DIR = APP_DIR / "uploads"
OUTPUT_DIR = APP_DIR / "outputs"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Video Editor")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/generate")
async def generate(
    prompt: str = Form(...),
    video: UploadFile | None = File(None),
):
    prompt = prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required.")

    saved_video: Path | None = None
    try:
        if video and video.filename:
            if not video.filename.lower().endswith(".mp4"):
                raise HTTPException(status_code=400, detail="Only .mp4 files are supported.")

            saved_video = UPLOAD_DIR / f"{uuid.uuid4().hex}.mp4"
            with saved_video.open("wb") as out:
                shutil.copyfileobj(video.file, out)

        output_path = video_editor_mod.process_request(
            prompt,
            video_path=saved_video,
            output_dir=OUTPUT_DIR,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if saved_video and saved_video.exists():
            saved_video.unlink(missing_ok=True)

    return FileResponse(
        path=output_path,
        media_type="video/mp4",
        filename="generated_video.mp4",
    )
