#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_CORPUS = Path(".local/dataagent/phase1/embedding-corpus.jsonl")
DEFAULT_CACHE = Path(".local/dataagent/phase1/embedding-cache.jsonl")
DEFAULT_LOG = Path(".local/dataagent/phase1/embedding-monitor.log")
DEFAULT_PID = Path(".local/dataagent/phase1/embedding-build.pid")


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor and restart full embedding build.")
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--pid-file", type=Path, default=DEFAULT_PID)
    args = parser.parse_args()

    args.log.parent.mkdir(parents=True, exist_ok=True)
    while True:
        status = check_status(args.pid_file)
        cached = valid_cache_count(DEFAULT_CACHE, DEFAULT_CORPUS)
        total = line_count(DEFAULT_CORPUS)
        if status["state"] != "running" and cached < total:
            proc = start_build(args.workers, args.batch_size)
            args.pid_file.write_text(str(proc.pid), encoding="utf-8")
            status = {"state": "restarted", "pid": proc.pid}
        record = {
            "ts": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "cached": cached,
            "total": total,
            "pct": round((cached / total * 100), 2) if total else 0,
            **status,
        }
        with args.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        if total and cached >= total:
            break
        time.sleep(args.interval_seconds)


def check_status(pid_file: Path) -> dict[str, object]:
    if not pid_file.exists():
        return {"state": "missing"}
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return {"state": "bad_pid"}
    result = subprocess.run(["ps", "-p", str(pid)], capture_output=True, text=True, check=False)
    if result.returncode == 0:
        return {"state": "running", "pid": pid}
    return {"state": "stopped", "pid": pid}


def start_build(workers: int, batch_size: int) -> subprocess.Popen[str]:
    log_path = Path(".local/dataagent/phase1/embedding-build.stdout.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("a", encoding="utf-8")
    command = [
        "python3",
        "scripts/build_embedding_index.py",
        "--corpus-manifest",
        ".planning/phases/01-data-architecture-research/embedding-corpus-manifest.json",
        "--manifest",
        ".planning/phases/01-data-architecture-research/embedding-index-manifest.json",
        "--build-log",
        ".planning/phases/01-data-architecture-research/embedding-index-build.md",
        "--cache",
        ".local/dataagent/phase1/embedding-cache.jsonl",
        "--batch-size",
        str(batch_size),
        "--workers",
        str(workers),
    ]
    return subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT, text=True)


def line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def valid_cache_count(cache_path: Path, corpus_path: Path) -> int:
    if not cache_path.exists() or not corpus_path.exists():
        return 0
    current_chunks = set()
    with corpus_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                current_chunks.add(json.loads(line)["chunk_id"])
    valid = set()
    with cache_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                chunk_id = json.loads(line).get("chunk_id")
                if chunk_id in current_chunks:
                    valid.add(chunk_id)
    return len(valid)


if __name__ == "__main__":
    main()
