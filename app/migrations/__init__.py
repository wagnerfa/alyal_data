"""Database migration helpers for lightweight schema updates."""

from typing import Callable, Iterable, Optional

from flask_sqlalchemy import SQLAlchemy

from .manager_note_company import ensure_manager_note_company_id


def run_all_migrations(
    db: SQLAlchemy, runners: Optional[Iterable[Callable[[SQLAlchemy], None]]] = None
) -> None:
    """Execute registered migration routines safely."""

    tasks: Iterable[Callable[[SQLAlchemy], None]]
    if runners is None:
        tasks = (ensure_manager_note_company_id,)
    else:
        tasks = tuple(runner for runner in runners if runner)

    for task in tasks:
        task(db)
