"""Video editing style analysis and Veo generation via Google Gemini."""

from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path

from google import genai

SKILL_FOLDER_NAME = "video-editing-style-skill"
SKILL_MANIFEST_NAME = "video-editing-style.md"
SKILL_PATH_ENV = "VIDEO_EDITING_STYLE_SKILL_PATH"
SKILLS_DIR_ENV = "SKILLS_DIR"
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
DEFAULT_VEO_MODEL = os.environ.get("VEO_MODEL", "veo-3.1-generate-preview")
UPLOAD_POLL_SEC = float(os.environ.get("GEMINI_UPLOAD_POLL_SEC", "2"))
OUTPUT_DIR = Path(os.environ.get("VIDEO_OUTPUT_DIR", "outputs"))

client = genai.Client()


def _module_dir() -> Path:
    return Path(__file__).resolve().parent


def _skill_search_paths() -> list[Path]:
    paths: list[Path] = []

    if env_path := os.environ.get(SKILL_PATH_ENV):
        paths.append(Path(env_path).expanduser())

    if skills_dir := os.environ.get(SKILLS_DIR_ENV):
        paths.append(Path(skills_dir).expanduser() / SKILL_FOLDER_NAME)

    paths.extend(
        [
            Path.home() / "skills" / SKILL_FOLDER_NAME,
            _module_dir() / "skills" / SKILL_FOLDER_NAME,
        ]
    )

    seen: set[Path] = set()
    unique_paths: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_paths.append(resolved)
    return unique_paths


def find_skill_manifest(skill_dir: Path) -> Path:
    matches = sorted(
        entry
        for entry in skill_dir.iterdir()
        if entry.is_file() and entry.name.lower() == SKILL_MANIFEST_NAME.lower()
    )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"Multiple {SKILL_MANIFEST_NAME} files found in {skill_dir}")

    raise FileNotFoundError(
        f"No {SKILL_MANIFEST_NAME} found in {skill_dir}. "
        f"Add the skill manifest as {SKILL_MANIFEST_NAME}."
    )


def resolve_skill_dir() -> Path:
    checked: list[str] = []
    for candidate in _skill_search_paths():
        checked.append(str(candidate))
        if not candidate.is_dir():
            continue
        try:
            find_skill_manifest(candidate)
        except (FileNotFoundError, ValueError):
            continue
        return candidate

    checked_list = "\n  - ".join(checked)
    raise FileNotFoundError(
        f"Could not find a valid {SKILL_FOLDER_NAME} folder with {SKILL_MANIFEST_NAME}. Checked:\n"
        f"  - {checked_list}\n"
        f"Set {SKILL_PATH_ENV} to the skill folder path, {SKILLS_DIR_ENV} to a "
        f"shared skills library, or install the skill to ~/skills/{SKILL_FOLDER_NAME}."
    )


def _read_manifest_text(skill_dir: Path) -> str:
    return find_skill_manifest(skill_dir).read_text(encoding="utf-8")


def read_skill_name(skill_dir: Path) -> str:
    match = re.search(r"^name:\s*(.+)$", _read_manifest_text(skill_dir), re.MULTILINE)
    if match:
        return match.group(1).strip().strip("\"'")
    return SKILL_FOLDER_NAME


def read_skill_instructions(skill_dir: Path) -> str:
    text = _read_manifest_text(skill_dir)
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text


def _validate_mp4(video_path: Path) -> Path:
    resolved = video_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Video file not found: {resolved}")
    if resolved.suffix.lower() != ".mp4":
        raise ValueError(f"Expected an .mp4 file, got: {resolved.name}")
    return resolved


def upload_mp4(video_path: Path):
    uploaded = client.files.upload(file=str(video_path))
    while uploaded.state == "PROCESSING":
        time.sleep(UPLOAD_POLL_SEC)
        uploaded = client.files.get(name=uploaded.name)

    if uploaded.state != "ACTIVE":
        raise RuntimeError(f"Video upload failed with state: {uploaded.state}")
    return uploaded


def analyze_editing_style(
    user_prompt: str,
    *,
    video_path: Path | None = None,
    model: str = DEFAULT_GEMINI_MODEL,
) -> str:
    skill_dir = resolve_skill_dir()
    skill_name = read_skill_name(skill_dir)
    skill_instructions = read_skill_instructions(skill_dir)

    user_message = (
        f"Follow the {skill_name} skill instructions below.\n\n"
        f"## Skill instructions\n\n{skill_instructions}\n\n"
        f"## User request\n\n{user_prompt.strip()}"
    )

    contents: list = [user_message]
    if video_path is not None:
        video_path = _validate_mp4(video_path)
        uploaded = upload_mp4(video_path)
        contents = [uploaded, user_message]

    response = client.models.generate_content(
        model=model,
        contents=contents,
    )
    return response.text or ""


def extract_veo_prompt(analysis_text: str, fallback_prompt: str) -> str:
    match = re.search(
        r"VEO PROMPT:\s*(.+)",
        analysis_text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return fallback_prompt.strip()


def generate_video(
    prompt: str,
    *,
    output_path: Path,
    model: str = DEFAULT_VEO_MODEL,
) -> Path:
    operation = client.models.generate_videos(
        model=model,
        prompt=prompt.strip(),
    )

    while not operation.done:
        time.sleep(10)
        operation = client.operations.get(operation)

    generated_video = operation.response.generated_videos[0]
    client.files.download(file=generated_video.video)
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated_video.video.save(str(output_path))
    return output_path


def process_request(
    prompt: str,
    *,
    video_path: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Analyze optional reference MP4, then generate and return output MP4 path."""
    output_dir = output_dir or OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{uuid.uuid4().hex}.mp4"

    veo_prompt = prompt.strip()
    if video_path is not None:
        analysis = analyze_editing_style(
            (
                f"{prompt.strip()}\n\n"
                "Produce a style guide and end with a single VEO PROMPT paragraph "
                "that captures this reference edit style applied to the user request."
            ),
            video_path=video_path,
        )
        veo_prompt = extract_veo_prompt(analysis, veo_prompt)

    return generate_video(veo_prompt, output_path=output_path)


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Generate a video from prompt + optional reference MP4.")
    parser.add_argument("--video", "-v", type=Path)
    parser.add_argument("--prompt", "-p", required=True)
    parser.add_argument("--output", "-o", type=Path, default=OUTPUT_DIR / "generated_video.mp4")
    args = parser.parse_args()

    try:
        if args.video:
            out = process_request(args.prompt, video_path=args.video, output_dir=args.output.parent)
        else:
            out = generate_video(args.prompt, output_path=args.output)
        print(f"Saved to {out}")
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
