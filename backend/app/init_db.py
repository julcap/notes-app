from sqlalchemy import text
from .database import Base, engine
from .auth import models as auth_models  # noqa: F401 - registers users/sessions tables with Base.metadata
from .notes import models as notes_models  # noqa: F401 - registers notes/attachments tables with Base.metadata
# Idempotent initial schema + upgrade for pre-auth local installs. Existing notes
# are preserved unassigned, never given to the next person who registers.
with engine.begin() as connection:
    connection.execute(text('SELECT pg_advisory_xact_lock(71938421)'))
    Base.metadata.create_all(connection)
    connection.execute(text('ALTER TABLE notes ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(id)'))
    connection.execute(text('CREATE INDEX IF NOT EXISTS ix_notes_owner_id ON notes(owner_id)'))
    # Enforce ownership on every future insert/update, while preserving old rows.
    exists=connection.execute(text("SELECT 1 FROM pg_constraint WHERE conname='notes_owner_required' AND conrelid='notes'::regclass")).scalar()
    if not exists:
        connection.execute(text('ALTER TABLE notes ADD CONSTRAINT notes_owner_required CHECK (owner_id IS NOT NULL) NOT VALID'))
