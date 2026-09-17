"""Establish the current schema and safely adopt known installations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text


revision = '20260917_0001'
down_revision = None
branch_labels = None
depends_on = None


CURRENT_COLUMNS = {
    'users': {'id', 'email', 'pending_email', 'password_hash', 'email_verified', 'display_name', 'auth_provider', 'token_version', 'totp_secret', 'totp_enabled', 'created_at', 'updated_at'},
    'social_identities': {'id', 'user_id', 'provider', 'provider_user_id'},
    'refresh_tokens': {'id', 'user_id', 'token_hash', 'csrf_hash', 'remember', 'expires_at', 'revoked_at'},
    'email_tokens': {'id', 'user_id', 'purpose', 'token_hash', 'expires_at', 'used_at'},
    'auth_rate_limits': {'key', 'hits', 'expires_at'},
    'backup_codes': {'id', 'user_id', 'code_hash', 'used_at', 'created_at'},
    'notes': {'id', 'owner_id', 'title', 'content', 'attendees', 'meeting_date', 'created_at', 'updated_at'},
    'attachments': {'id', 'note_id', 'filename', 'size', 'created_at'},
    'action_items': {'id', 'note_id', 'text', 'owner_name', 'due_date', 'done', 'created_at'},
}
LEGACY_COLUMNS = {
    'notes': CURRENT_COLUMNS['notes'] - {'owner_id'},
    'attachments': CURRENT_COLUMNS['attachments'],
}
EXPECTED_PRIMARY_KEYS = {
    **{table: ('id',) for table in CURRENT_COLUMNS if table != 'auth_rate_limits'},
    'auth_rate_limits': ('key',),
}
EXPECTED_NULLABLE = {
    'users': {'pending_email', 'password_hash', 'totp_secret'},
    'refresh_tokens': {'revoked_at'},
    'email_tokens': {'used_at'},
    'backup_codes': {'used_at'},
    'notes': set(),
    'action_items': {'due_date'},
}
EXPECTED_UNIQUE_CONSTRAINTS = {
    'social_identities': {('provider', 'provider_user_id')},
    'refresh_tokens': {('token_hash',)},
    'email_tokens': {('token_hash',)},
}
EXPECTED_FOREIGN_KEYS = {
    'social_identities': {('user_id', 'users', 'id')},
    'refresh_tokens': {('user_id', 'users', 'id')},
    'email_tokens': {('user_id', 'users', 'id')},
    'backup_codes': {('user_id', 'users', 'id')},
    'notes': {('owner_id', 'users', 'id')},
    'attachments': {('note_id', 'notes', 'id')},
    'action_items': {('note_id', 'notes', 'id')},
}
EXPECTED_INDEXES = {
    'users': {'ix_users_email', 'unique_local_email'},
    'social_identities': {'ix_social_identities_user_id'},
    'refresh_tokens': {'ix_refresh_tokens_user_id'},
    'email_tokens': {'ix_email_tokens_user_id'},
    'backup_codes': {'ix_backup_codes_user_id'},
    'notes': {'ix_notes_owner_id'},
    'attachments': {'ix_attachments_note_id'},
    'action_items': {'ix_action_items_note_id'},
}


def _tables(inspector):
    return set(inspector.get_table_names()) - {'alembic_version'}


def _foreign_keys(inspector, table):
    keys = set()
    for item in inspector.get_foreign_keys(table):
        if len(item['constrained_columns']) == 1 and len(item['referred_columns']) == 1:
            keys.add((item['constrained_columns'][0], item['referred_table'], item['referred_columns'][0]))
    return keys


def _has_owner_check(connection):
    return connection.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = 'notes'::regclass
              AND conname = 'notes_owner_required'
              AND contype = 'c'
        )
    """)).scalar_one()


def _validate_legacy(inspector):
    if _tables(inspector) != set(LEGACY_COLUMNS):
        return False
    for table, columns in LEGACY_COLUMNS.items():
        reflected = inspector.get_columns(table)
        if {column['name'] for column in reflected} != columns:
            return False
        if any(column['nullable'] for column in reflected):
            return False
        if tuple(inspector.get_pk_constraint(table)['constrained_columns']) != ('id',):
            return False
    attachment_key = ('note_id', 'notes', 'id')
    indexes = {index['name'] for index in inspector.get_indexes('attachments')}
    return attachment_key in _foreign_keys(inspector, 'attachments') and 'ix_attachments_note_id' in indexes


def _validate_current(connection, inspector):
    if _tables(inspector) != set(CURRENT_COLUMNS):
        return False
    owner_is_nullable = False
    for table, expected in CURRENT_COLUMNS.items():
        reflected = inspector.get_columns(table)
        if {column['name'] for column in reflected} != expected:
            return False
        nullable = {column['name'] for column in reflected if column['nullable']}
        if table == 'notes' and 'owner_id' in nullable:
            owner_is_nullable = True
            nullable.remove('owner_id')
        if nullable != EXPECTED_NULLABLE.get(table, set()):
            return False
        primary_key = tuple(inspector.get_pk_constraint(table)['constrained_columns'])
        if primary_key != EXPECTED_PRIMARY_KEYS[table]:
            return False
        if not EXPECTED_FOREIGN_KEYS.get(table, set()).issubset(_foreign_keys(inspector, table)):
            return False
        indexes = {index['name'] for index in inspector.get_indexes(table)}
        if not EXPECTED_INDEXES.get(table, set()).issubset(indexes):
            return False
        unique_constraints = {
            tuple(constraint['column_names'])
            for constraint in inspector.get_unique_constraints(table)
        }
        if not EXPECTED_UNIQUE_CONSTRAINTS.get(table, set()).issubset(unique_constraints):
            return False
    return not owner_is_nullable or _has_owner_check(connection)


def _create_user_tables():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(320), nullable=False),
        sa.Column('pending_email', sa.String(320), nullable=True),
        sa.Column('password_hash', sa.String(100), nullable=True),
        sa.Column('email_verified', sa.Boolean(), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('auth_provider', sa.String(20), nullable=False),
        sa.Column('token_version', sa.Integer(), nullable=False),
        sa.Column('totp_secret', sa.String(200), nullable=True),
        sa.Column('totp_enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('unique_local_email', 'users', ['email'], unique=True, postgresql_where=text("auth_provider = 'local'"))
    op.create_table(
        'social_identities',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('provider_user_id', sa.String(255), nullable=False),
        sa.UniqueConstraint('provider', 'provider_user_id'),
    )
    op.create_index('ix_social_identities_user_id', 'social_identities', ['user_id'])
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('csrf_hash', sa.String(64), nullable=False),
        sa.Column('remember', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])
    op.create_table(
        'email_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('purpose', sa.String(20), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_email_tokens_user_id', 'email_tokens', ['user_id'])
    op.create_table(
        'auth_rate_limits',
        sa.Column('key', sa.String(64), primary_key=True),
        sa.Column('hits', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'backup_codes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('code_hash', sa.String(100), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_backup_codes_user_id', 'backup_codes', ['user_id'])


def _create_notes(owner_nullable):
    op.create_table(
        'notes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=owner_nullable),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('attendees', sa.String(1000), nullable=False),
        sa.Column('meeting_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('owner_id IS NOT NULL', name='notes_owner_required'),
    )
    op.create_index('ix_notes_owner_id', 'notes', ['owner_id'])


def _create_attachments():
    op.create_table(
        'attachments',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('note_id', sa.String(36), sa.ForeignKey('notes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_attachments_note_id', 'attachments', ['note_id'])


def _create_action_items():
    op.create_table(
        'action_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('note_id', sa.String(36), sa.ForeignKey('notes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('text', sa.String(500), nullable=False),
        sa.Column('owner_name', sa.String(200), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('done', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_action_items_note_id', 'action_items', ['note_id'])


def _create_clean_schema():
    _create_user_tables()
    _create_notes(owner_nullable=False)
    _create_attachments()
    _create_action_items()


def _upgrade_legacy_schema():
    _create_user_tables()
    op.add_column('notes', sa.Column('owner_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_notes_owner_id_users', 'notes', 'users', ['owner_id'], ['id'])
    op.create_index('ix_notes_owner_id', 'notes', ['owner_id'])
    op.execute('ALTER TABLE notes ADD CONSTRAINT notes_owner_required CHECK (owner_id IS NOT NULL) NOT VALID')
    _create_action_items()


def upgrade():
    connection = op.get_bind()
    inspector = inspect(connection)
    tables = _tables(inspector)
    if not tables:
        _create_clean_schema()
        return
    if _validate_legacy(inspector):
        _upgrade_legacy_schema()
        return
    if _validate_current(connection, inspector):
        return
    raise RuntimeError('Unsupported database schema; refusing to stamp unknown drift')


def downgrade():
    for table in ('action_items', 'attachments', 'notes', 'backup_codes', 'auth_rate_limits', 'email_tokens', 'refresh_tokens', 'social_identities', 'users'):
        op.drop_table(table)
