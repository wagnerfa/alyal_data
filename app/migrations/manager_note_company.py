"""Migration helpers for ManagerNote.company_id backfill."""

from typing import List, Sequence

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text


def _fetch_company_ids(db: SQLAlchemy) -> List[int]:
    result = db.session.execute(
        text("SELECT id FROM user WHERE role = 'user' ORDER BY id")
    )
    return [row[0] for row in result]


def ensure_manager_note_company_id(db: SQLAlchemy) -> None:
    """Add the company_id column and backfill existing notes."""

    inspector = inspect(db.engine)
    columns = {col['name'] for col in inspector.get_columns('manager_note')}

    if 'company_id' not in columns:
        db.session.execute(
            text('ALTER TABLE manager_note ADD COLUMN company_id INTEGER REFERENCES user(id)')
        )
        db.session.execute(
            text('CREATE INDEX IF NOT EXISTS ix_manager_note_company_id ON manager_note (company_id)')
        )
        db.session.commit()

    notes_without_company: Sequence = db.session.execute(
        text(
            'SELECT id, periodo_inicio, periodo_fim, conteudo, author_id '
            'FROM manager_note WHERE company_id IS NULL'
        )
    ).fetchall()

    if not notes_without_company:
        return

    company_ids = _fetch_company_ids(db)
    if not company_ids:
        # Without companies we cannot meaningfully backfill the data.
        return

    primary_company_id = company_ids[0]

    for note in notes_without_company:
        note_data = note._mapping if hasattr(note, '_mapping') else note
        db.session.execute(
            text(
                'UPDATE manager_note SET company_id = :company_id WHERE id = :note_id'
            ),
            {'company_id': primary_company_id, 'note_id': note_data['id']},
        )

        for company_id in company_ids[1:]:
            db.session.execute(
                text(
                    'INSERT INTO manager_note '
                    '(periodo_inicio, periodo_fim, conteudo, author_id, company_id) '
                    'VALUES (:inicio, :fim, :conteudo, :author_id, :company_id)'
                ),
                {
                    'inicio': note_data['periodo_inicio'],
                    'fim': note_data['periodo_fim'],
                    'conteudo': note_data['conteudo'],
                    'author_id': note_data['author_id'],
                    'company_id': company_id,
                },
            )

    db.session.commit()
