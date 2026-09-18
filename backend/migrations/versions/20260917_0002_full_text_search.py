"""Add weighted PostgreSQL full-text search to notes."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '20260917_0002'
down_revision = '20260917_0001'
branch_labels = None
depends_on = None


SEARCH_VECTOR_EXPRESSION = """
setweight(
    to_tsvector('pg_catalog.simple'::regconfig, coalesce(title, '')),
    'A'
) || setweight(
    to_tsvector('pg_catalog.simple'::regconfig, coalesce(attendees, '')),
    'B'
) || setweight(
    to_tsvector('pg_catalog.simple'::regconfig, coalesce(content, '')),
    'C'
)
"""


def upgrade():
    op.add_column(
        'notes',
        sa.Column(
            'search_vector',
            postgresql.TSVECTOR(),
            sa.Computed(SEARCH_VECTOR_EXPRESSION, persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        'ix_notes_search_vector',
        'notes',
        ['search_vector'],
        postgresql_using='gin',
    )


def downgrade():
    op.drop_index('ix_notes_search_vector', table_name='notes')
    op.drop_column('notes', 'search_vector')
