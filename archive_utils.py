"""Verifiable study archive and transactional reset primitives."""

import csv
import hashlib
import io
import json
import platform
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import CONSENT_VERSION, EXPERIMENT_VERSION, PROMPT_VERSION
from db_utils import get_connection, using_postgres


STUDY_TABLES = (
    "v5_releases", "v5_blocks", "v5_participants", "v5_identities",
    "v5_periods", "v5_responses", "v5_exchanges", "v5_requests",
    "v5_predictions", "v5_measures", "v5_consultation_events", "v5_transitions",
    "participants",
    "study_sessions_v2",
    "responses_v2",
    "chat_events_v2",
    "paper_metrics_v4",
    "item_timing_v4",
    "study_events_v4",
    "participant_identity_v2",
)
DELETE_ORDER = (
    "study_events_v4",
    "item_timing_v4",
    "paper_metrics_v4",
    "chat_events_v2",
    "responses_v2",
    "participant_identity_v2",
    "study_sessions_v2",
    "participants",
)


def _table_exists(connection, table: str) -> bool:
    if using_postgres():
        row = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = %s) AS present",
            (table,),
        ).fetchone()
        return bool(row["present"])
    row = connection.execute(
        "SELECT 1 AS present FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return bool(row)


def _columns(connection, table: str) -> list[dict[str, Any]]:
    if not _table_exists(connection, table):
        return []
    if using_postgres():
        rows = connection.execute(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_schema = current_schema() "
            "AND table_name = %s ORDER BY ordinal_position",
            (table,),
        ).fetchall()
        return [dict(row) for row in rows]
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return [dict(row) for row in rows]


def _csv_bytes(columns: list[str], rows: list[dict[str, Any]]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_manifest(manifest: dict[str, Any]) -> bytes:
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_archive_bytes(*, experiment_version: Optional[str] = None, prompt_version: Optional[str] = None) -> tuple[bytes, dict[str, Any], str]:
    """Snapshot all legacy, V3, and V4 tables into a checksummed ZIP."""
    files: dict[str, bytes] = {}
    table_manifest: dict[str, Any] = {}
    connection = get_connection()
    try:
        with connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY" if using_postgres() else "BEGIN")
            for table in STUDY_TABLES:
                schema = _columns(connection, table)
                columns = [item.get("column_name", item.get("name")) for item in schema]
                if _table_exists(connection, table):
                    rows = [dict(row) for row in connection.execute(f"SELECT * FROM {table}").fetchall()]
                else:
                    rows = []
                csv_name = f"tables/{table}.csv"
                schema_name = f"schemas/{table}.json"
                files[csv_name] = _csv_bytes(columns, rows) if columns else b""
                files[schema_name] = json.dumps(schema, indent=2, default=str).encode("utf-8")
                table_manifest[table] = {
                    "exists": bool(schema),
                    "row_count": len(rows),
                    "columns": columns,
                    "csv": csv_name,
                    "schema": schema_name,
                }
    finally:
        connection.close()

    manifest = {
        "archive_format": "humanai-study-backup-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database_driver": "postgresql" if using_postgres() else "sqlite",
        "python_version": platform.python_version(),
        "experiment_version": experiment_version or EXPERIMENT_VERSION,
        "consent_version": CONSENT_VERSION,
        "prompt_version": prompt_version or PROMPT_VERSION,
        "tables": table_manifest,
        "files": {name: {"sha256": _sha(data), "bytes": len(data)} for name, data in files.items()},
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    token = _sha(_canonical_manifest(manifest))
    files["manifest.json"] = manifest_bytes
    files["MANIFEST_SHA256.txt"] = (token + "\n").encode("ascii")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    archive_bytes = output.getvalue()
    verify_archive_bytes(archive_bytes, expected_token=token)
    return archive_bytes, manifest, token


def verify_archive_bytes(data: bytes, expected_token: Optional[str] = None) -> dict[str, Any]:
    """Re-read every archived file and validate checksum and row-count evidence."""
    with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        token = _sha(_canonical_manifest(manifest))
        stored_token = archive.read("MANIFEST_SHA256.txt").decode("ascii").strip()
        if stored_token != token or (expected_token and expected_token != token):
            raise ValueError("Archive manifest hash does not match.")
        for name, evidence in manifest["files"].items():
            content = archive.read(name)
            if _sha(content) != evidence["sha256"] or len(content) != evidence["bytes"]:
                raise ValueError(f"Archive verification failed for {name}.")
        for table, evidence in manifest["tables"].items():
            csv_data = archive.read(evidence["csv"]).decode("utf-8")
            count = sum(1 for _ in csv.DictReader(io.StringIO(csv_data))) if csv_data else 0
            if count != evidence["row_count"]:
                raise ValueError(f"Archive row count failed for {table}.")
    return manifest


def write_verified_archive(output_dir: Path) -> tuple[Path, str, dict[str, Any]]:
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    data, manifest, token = build_archive_bytes()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"humanai-study-backup-{stamp}.zip"
    path.write_bytes(data)
    verify_archive_bytes(path.read_bytes(), expected_token=token)
    return path, token, manifest


def reset_from_verified_archive(archive_path: Path, confirmation_token: str) -> dict[str, int]:
    data = archive_path.expanduser().resolve().read_bytes()
    manifest = verify_archive_bytes(data, expected_token=confirmation_token)
    if _sha(_canonical_manifest(manifest)) != confirmation_token:
        raise ValueError("Reset confirmation token refused.")
    connection = get_connection()
    try:
        with connection:
            if using_postgres():
                existing = [table for table in STUDY_TABLES if _table_exists(connection, table)]
                if existing:
                    connection.execute("LOCK TABLE " + ", ".join(existing) + " IN ACCESS EXCLUSIVE MODE")
            else:
                connection.execute("BEGIN IMMEDIATE")
            for table in DELETE_ORDER:
                if _table_exists(connection, table):
                    connection.execute(f"DELETE FROM {table}")
            counts = {}
            for table in STUDY_TABLES:
                if _table_exists(connection, table):
                    counts[table] = int(connection.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"])
                else:
                    counts[table] = 0
            if any(counts.values()):
                raise RuntimeError(f"Reset verification failed: {counts}")
    finally:
        connection.close()
    return counts
