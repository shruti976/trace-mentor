"""Small database adapter shared by the versioned study and archive tools."""

import sqlite3

from config import DATABASE_URL, EXPERIMENT_DB


def using_postgres() -> bool:
    return bool(DATABASE_URL.strip())


def db_placeholder() -> str:
    return "%s" if using_postgres() else "?"


def db_query(query: str) -> str:
    return query.replace("?", "%s") if using_postgres() else query


def get_connection():
    if using_postgres():
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("DATABASE_URL is set, but psycopg is not installed. Install requirements.txt.") from exc
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    EXPERIMENT_DB.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(EXPERIMENT_DB)
    connection.row_factory = sqlite3.Row
    return connection
