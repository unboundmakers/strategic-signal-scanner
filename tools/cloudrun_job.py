#!/usr/bin/env python3
"""Cloud Run Job: capture, score and persist private JSON artifacts."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))


def main() -> int:
    private_bucket = _bucket_config()
    score_mode, model, min_score = _scoring_config()
    fixture = _env("FIXTURE_FEED")
    if fixture:
        if score_mode != "mock" or private_bucket:
            raise ValueError("Fixture runs require mock mode and no cloud destination.")
    elif not _env_bool("ALLOW_NETWORK", False):
        raise ValueError("Set FIXTURE_FEED for offline runs, or ALLOW_NETWORK=true for live capture.")
    output_dir = _env_path("OUTPUT_DIR", "/tmp/artifacts/rss")
    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_previous_outputs(output_dir)
    os.environ.setdefault("STATE_PATH", str(output_dir / "state.json"))
    state_path = Path(os.environ["STATE_PATH"]).expanduser().resolve()
    private_prefix = _env("PRIVATE_ARTIFACT_PREFIX", "signal-private").strip("/")

    print("Cloud Run Job started.", flush=True)
    print(f"  output_dir={output_dir}", flush=True)
    print(f"  score_mode={score_mode}", flush=True)
    print(f"  model={model}", flush=True)
    if private_bucket:
        _download_state_from_bucket(private_bucket, private_prefix, state_path)

    command = [
        sys.executable, "-B", str(SCRIPT_DIR / "capture_and_score.py"),
        "--group", _env("RUN_GROUP", "cloudrun"),
        "--items-per-feed", _env("ITEMS_PER_FEED", "1"),
        "--max-articles", _env("MAX_ARTICLES", "30"),
        "--output-dir", str(output_dir), "--score-mode", score_mode,
        "--model", model, "--retry-attempts", _env("RETRY_ATTEMPTS", "5"),
        "--min-score", min_score,
    ]
    if fixture:
        command.extend(["--fixture-feed", fixture])
    else:
        command.append("--allow-network")
    if _env_bool("IGNORE_STATE", False):
        command.append("--ignore-state")
    _run(command, cwd=SCRIPT_DIR)

    if not any(output_dir.glob("scored_*.json")):
        print("No scored JSON was generated.", file=sys.stderr)
        return 1
    if private_bucket:
        _mirror_state_into_output_dir(state_path, output_dir)
        _upload_artifacts(output_dir, private_bucket, private_prefix)
    else:
        print("PRIVATE_ARTIFACT_BUCKET not set; keeping JSON artifacts local only.", flush=True)
    print("Cloud Run Job finished successfully.", flush=True)
    return 0


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else default


def _bucket_config() -> str:
    obsolete = ("ARCHIVE_BUCKET", "ARCHIVE_PREFIX", "REPORT_MAX_AGE_DAYS", "MAX_AGE_DAYS")
    if any(_env(name) for name in obsolete):
        raise ValueError("HTML report export is not supported; remove obsolete report settings.")
    private = _env("PRIVATE_ARTIFACT_BUCKET")
    if private and (private.startswith("gs:") or "/" in private or "\\" in private):
        raise ValueError("Use a bare private bucket name, not a URL or path")
    return private


def _scoring_config() -> tuple[str, str, str]:
    score_mode = _env("SCORE_MODE", "mock")
    if score_mode not in {"mock", "gemini", "deepseek"}:
        raise ValueError("SCORE_MODE must be mock, gemini or deepseek")
    if _env("MODEL"):
        model = _env("MODEL")
    elif score_mode == "gemini":
        model = _env("GEMINI_MODEL", "gemini-2.5-flash")
    else:
        model = _env("DEEPSEEK_MODEL", "deepseek-chat")
    return score_mode, model, _env("MIN_SCORE", "4")


def _env_bool(name: str, default: bool = False) -> bool:
    return _env(name, "true" if default else "false").lower() in {"1", "true", "yes", "on"}


def _env_path(name: str, default: str) -> Path:
    path = Path(_env(name, default))
    return path if path.is_absolute() else REPO_DIR / path


def _clear_previous_outputs(output_dir: Path) -> None:
    for pattern in ("raw_*.json", "scored_*.json"):
        for path in output_dir.glob(pattern):
            try:
                path.unlink()
            except FileNotFoundError:
                continue


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"Running: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode:
        raise SystemExit(result.returncode)


def _storage_client():
    try:
        from google.cloud import storage
    except ImportError as exc:
        raise RuntimeError("google-cloud-storage is required for private JSON persistence.") from exc
    return storage.Client()


def _download_json(bucket_name: str, prefix: str, path: Path, filename: str) -> None:
    name = f"{prefix}/{filename}" if prefix else filename
    blob = _storage_client().bucket(bucket_name).get_blob(name)
    if blob is None:
        print(f"No remote {filename}; starting fresh.", flush=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(str(path))


def _download_state_from_bucket(bucket_name: str, prefix: str, state_path: Path) -> None:
    _download_json(bucket_name, prefix, state_path, "state.json")




def _mirror_json(path: Path, output_dir: Path, filename: str) -> None:
    target = output_dir / filename
    if path.exists() and target.resolve() != path.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _mirror_state_into_output_dir(state_path: Path, output_dir: Path) -> None:
    _mirror_json(state_path, output_dir, "state.json")




def _upload_artifacts(output_dir: Path, bucket_name: str, prefix: str) -> None:
    """Only upload allowlisted JSON to the explicitly configured private bucket."""
    private = _bucket_config()
    if not private or bucket_name != private:
        raise ValueError("JSON upload requires the configured PRIVATE_ARTIFACT_BUCKET")
    bucket = _storage_client().bucket(bucket_name)
    for path in sorted(output_dir.iterdir()):
        if not path.is_file() or path.is_symlink():
            continue
        allowed = (path.name == "state.json" or
                   (path.name.startswith(("raw_", "scored_")) and path.suffix == ".json"))
        if not allowed:
            continue
        name = f"{prefix}/{path.name}" if prefix else path.name
        blob = bucket.blob(name)
        blob.cache_control = "no-cache, max-age=0"
        blob.upload_from_filename(str(path), content_type="application/json; charset=utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
