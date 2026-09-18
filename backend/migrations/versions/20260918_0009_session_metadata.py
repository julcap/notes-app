import sqlalchemy as sa
from alembic import op


revision = '20260918_0009'
down_revision = '20260918_0008'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('refresh_tokens', sa.Column('token_version', sa.Integer(), nullable=True))
    op.execute(sa.text("""
        UPDATE refresh_tokens
        SET token_version = users.token_version
        FROM users
        WHERE users.id = refresh_tokens.user_id
    """))
    op.execute(sa.text("""
        CREATE FUNCTION refresh_tokens_inherit_token_version()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.token_version IS NULL THEN
                SELECT token_version
                INTO NEW.token_version
                FROM users
                WHERE id = NEW.user_id;
            END IF;
            RETURN NEW;
        END;
        $$
    """))
    op.execute(sa.text("""
        CREATE TRIGGER refresh_tokens_inherit_token_version
        BEFORE INSERT OR UPDATE OF user_id ON refresh_tokens
        FOR EACH ROW
        EXECUTE FUNCTION refresh_tokens_inherit_token_version()
    """))
    op.alter_column('refresh_tokens', 'token_version', nullable=False)
    op.add_column('refresh_tokens', sa.Column('user_agent', sa.String(length=512), nullable=True))
    op.add_column('refresh_tokens', sa.Column('ip_address', sa.String(length=45), nullable=True))
    op.add_column('refresh_tokens', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('refresh_tokens', sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('refresh_tokens', 'last_used_at')
    op.drop_column('refresh_tokens', 'created_at')
    op.drop_column('refresh_tokens', 'ip_address')
    op.drop_column('refresh_tokens', 'user_agent')
    op.execute(sa.text(
        'DROP TRIGGER refresh_tokens_inherit_token_version ON refresh_tokens'
    ))
    op.execute(sa.text('DROP FUNCTION refresh_tokens_inherit_token_version()'))
    op.drop_column('refresh_tokens', 'token_version')