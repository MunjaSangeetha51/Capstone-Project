"""Shared MySQL connection factory for optional database-backed features."""
from __future__ import annotations

import os

from fastapi import HTTPException


def is_mysql_configured() -> bool:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return all(os.getenv(name) for name in ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD"))


def connect_mysql():
    if not is_mysql_configured():
        raise HTTPException(status_code=503, detail="MySQL is not configured. Set MYSQL_HOST, MYSQL_USER, and MYSQL_PASSWORD.")
    try:
        import pymysql
        from pymysql.cursors import DictCursor

        return pymysql.connect(
            host=os.environ["MYSQL_HOST"],
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.environ["MYSQL_USER"],
            password=os.environ["MYSQL_PASSWORD"],
            database=os.getenv("MYSQL_DATABASE", "skillproof"),
            charset="utf8mb4",
            cursorclass=DictCursor,
            connect_timeout=5,
            autocommit=False,
        )
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="MySQL driver is missing. Install requirements.txt.") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Unable to connect to the configured MySQL database.") from exc
