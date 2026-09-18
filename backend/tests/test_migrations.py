import os
from pathlib import Path
import subprocess
import sys

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.migrations import upgrade_database


DATABASE_URL = os.environ['DATABASE_URL']


def reset_database():
    database = create_engine(DATABASE_URL)
    with database.begin() as connection:
        connection.execute(text('DROP SCHEMA public CASCADE'))
        connection.execute(text('CREATE SCHEMA public'))
    database.dispose()


def revision(database):
    with database.connect() as connection:
        return connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()


def migration_config():
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / 'alembic.ini'))
    config.set_main_option('script_location', str(backend / 'migrations'))
    config.set_main_option('sqlalchemy.url', DATABASE_URL)
    return config


def test_empty_database_upgrade_creates_current_schema():
    reset_database()

    upgrade_database(DATABASE_URL)

    database = create_engine(DATABASE_URL)
    schema = inspect(database)
    assert set(schema.get_table_names()) == {
        'action_items',
        'alembic_version',
        'attachments',
        'auth_rate_limits',
        'backup_codes',
        'email_tokens',
        'notes',
        'notification_deliveries',
        'refresh_tokens',
        'social_identities',
        'users',
    }
    assert {column['name']: column['nullable'] for column in schema.get_columns('notes')}['owner_id'] is False
    assert revision(database) == '20260918_0005'
    database.dispose()


def test_current_schema_adoption_preserves_populated_rows():
    reset_database()
    database = create_engine(DATABASE_URL)
    command.upgrade(migration_config(), '20260917_0001')
    with database.begin() as connection:
        connection.execute(text('DROP TABLE alembic_version'))
        user_id = connection.execute(text("""
            INSERT INTO users (
                email, pending_email, password_hash, email_verified, display_name,
                auth_provider, token_version, totp_secret, totp_enabled, created_at, updated_at
            ) VALUES (
                'kept@example.com', NULL, 'hash', true, 'Kept', 'local', 0, NULL, false, now(), now()
            ) RETURNING id
        """)).scalar_one()
        connection.execute(text("""
            INSERT INTO notes (id, owner_id, title, content, attendees, meeting_date, created_at, updated_at)
            VALUES ('note-kept', :owner_id, 'Kept note', 'body', '', current_date, now(), now())
        """), {'owner_id': user_id})
        connection.execute(text("""
            INSERT INTO attachments (id, note_id, filename, size, created_at)
            VALUES ('attachment-kept', 'note-kept', 'kept.txt', 4, now())
        """))
        connection.execute(text("""
            INSERT INTO action_items (id, note_id, text, owner_name, due_date, done, created_at)
            VALUES ('action-kept', 'note-kept', 'Keep this', '', NULL, false, now())
        """))

    upgrade_database(DATABASE_URL)

    with database.connect() as connection:
        assert connection.execute(text('SELECT email FROM users')).scalar_one() == 'kept@example.com'
        assert connection.execute(text('SELECT title FROM notes')).scalar_one() == 'Kept note'
        assert connection.execute(text('SELECT filename FROM attachments')).scalar_one() == 'kept.txt'
        assert connection.execute(text('SELECT text FROM action_items')).scalar_one() == 'Keep this'
    assert revision(database) == '20260918_0005'
    database.dispose()


def test_known_ownerless_legacy_schema_is_migrated_without_claiming_notes():
    reset_database()
    database = create_engine(DATABASE_URL)
    with database.begin() as connection:
        connection.execute(text("""
            CREATE TABLE notes (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                content TEXT NOT NULL,
                attendees VARCHAR(1000) NOT NULL,
                meeting_date DATE NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
        """))
        connection.execute(text("""
            CREATE TABLE attachments (
                id VARCHAR(36) PRIMARY KEY,
                note_id VARCHAR(36) NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                filename VARCHAR(255) NOT NULL,
                size INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
        """))
        connection.execute(text('CREATE INDEX ix_attachments_note_id ON attachments(note_id)'))
        connection.execute(text("""
            INSERT INTO notes (id, title, content, attendees, meeting_date, created_at, updated_at)
            VALUES ('legacy-note', 'Legacy', 'preserve me', '', current_date, now(), now())
        """))
        connection.execute(text("""
            INSERT INTO attachments (id, note_id, filename, size, created_at)
            VALUES ('legacy-attachment', 'legacy-note', 'legacy.txt', 8, now())
        """))

    upgrade_database(DATABASE_URL)

    with database.connect() as connection:
        assert connection.execute(text("SELECT owner_id FROM notes WHERE id='legacy-note'")).scalar_one_or_none() is None
        assert connection.execute(text("SELECT filename FROM attachments WHERE id='legacy-attachment'")).scalar_one() == 'legacy.txt'
        constraint = connection.execute(text("""
            SELECT convalidated
            FROM pg_constraint
            WHERE conrelid = 'notes'::regclass AND conname = 'notes_owner_required'
        """)).scalar_one()
        assert constraint is False
        with pytest.raises(Exception):
            with connection.begin():
                connection.execute(text("""
                    INSERT INTO notes (id, owner_id, title, content, attendees, meeting_date, created_at, updated_at)
                    VALUES ('new-ownerless', NULL, 'Rejected', '', '', current_date, now(), now())
                """))
    assert revision(database) == '20260918_0005'
    database.dispose()


def test_unknown_schema_drift_is_rejected_without_stamping():
    reset_database()
    database = create_engine(DATABASE_URL)
    with database.begin() as connection:
        connection.execute(text('CREATE TABLE notes (id INTEGER PRIMARY KEY, unexpected TEXT)'))

    with pytest.raises(RuntimeError, match='Unsupported database schema'):
        upgrade_database(DATABASE_URL)

    assert 'alembic_version' not in inspect(database).get_table_names()
    database.dispose()


def test_repeated_upgrade_is_a_no_op():
    reset_database()

    upgrade_database(DATABASE_URL)
    upgrade_database(DATABASE_URL)

    database = create_engine(DATABASE_URL)
    assert revision(database) == '20260918_0005'
    database.dispose()


def test_full_text_search_migration_adds_weighted_generated_vector_and_gin_index():
    reset_database()
    upgrade_database(DATABASE_URL)
    database = create_engine(DATABASE_URL)

    with database.connect() as connection:
        generated = connection.execute(text("""
            SELECT pg_get_expr(definition.adbin, definition.adrelid)
            FROM pg_attribute AS attribute
            JOIN pg_attrdef AS definition
              ON definition.adrelid = attribute.attrelid
             AND definition.adnum = attribute.attnum
            WHERE attribute.attrelid = 'notes'::regclass
              AND attribute.attname = 'search_vector'
              AND attribute.attgenerated = 's'
        """)).scalar_one()
        index_definition = connection.execute(text("""
            SELECT indexdef
            FROM pg_indexes
            WHERE tablename = 'notes' AND indexname = 'ix_notes_search_vector'
        """)).scalar_one()

    assert "setweight(to_tsvector('simple'::regconfig, (COALESCE(title, ''::character varying))::text), 'A'::\"char\")" in generated
    assert "setweight(to_tsvector('simple'::regconfig, (COALESCE(attendees, ''::character varying))::text), 'B'::\"char\")" in generated
    assert "setweight(to_tsvector('simple'::regconfig, COALESCE(content, ''::text)), 'C'::\"char\")" in generated
    assert 'USING gin (search_vector)' in index_definition
    database.dispose()


def test_full_text_search_migration_downgrade_and_upgrade_round_trip():
    reset_database()
    upgrade_database(DATABASE_URL)
    database = create_engine(DATABASE_URL)

    command.downgrade(migration_config(), '20260917_0001')
    assert 'search_vector' not in {column['name'] for column in inspect(database).get_columns('notes')}
    assert 'ix_notes_search_vector' not in {index['name'] for index in inspect(database).get_indexes('notes')}

    command.upgrade(migration_config(), 'head')
    assert 'search_vector' in {column['name'] for column in inspect(database).get_columns('notes')}
    assert 'ix_notes_search_vector' in {index['name'] for index in inspect(database).get_indexes('notes')}
    assert revision(database) == '20260918_0005'
    database.dispose()


def test_soft_delete_migration_adds_nullable_timezone_column_and_index():
    reset_database()
    upgrade_database(DATABASE_URL)
    database = create_engine(DATABASE_URL)

    deleted_at = next(column for column in inspect(database).get_columns('notes') if column['name'] == 'deleted_at')
    indexes = {index['name'] for index in inspect(database).get_indexes('notes')}

    assert deleted_at['nullable'] is True
    assert deleted_at['type'].timezone is True
    assert 'ix_notes_deleted_at' in indexes
    assert revision(database) == '20260918_0005'
    database.dispose()


def test_attachment_content_type_migration_defaults_legacy_rows():
    reset_database()
    database = create_engine(DATABASE_URL)
    command.upgrade(migration_config(), '20260917_0003')
    with database.begin() as connection:
        user_id = connection.execute(text("""
            INSERT INTO users (
                email, pending_email, password_hash, email_verified, display_name,
                auth_provider, token_version, totp_secret, totp_enabled, created_at, updated_at
            ) VALUES (
                'legacy@example.com', NULL, 'hash', true, 'Legacy', 'local', 0, NULL, false, now(), now()
            ) RETURNING id
        """)).scalar_one()
        connection.execute(text("""
            INSERT INTO notes (
                id, owner_id, title, content, attendees, meeting_date, created_at, updated_at
            ) VALUES (
                'legacy-note', :owner_id, 'Legacy', '', '', current_date, now(), now()
            )
        """), {'owner_id': user_id})
        connection.execute(text("""
            INSERT INTO attachments (id, note_id, filename, size, created_at)
            VALUES ('legacy-file', 'legacy-note', 'unknown.bin', 3, now())
        """))

    command.upgrade(migration_config(), 'head')

    content_type = next(
        column for column in inspect(database).get_columns('attachments')
        if column['name'] == 'content_type'
    )
    with database.connect() as connection:
        legacy_type = connection.execute(text(
            "SELECT content_type FROM attachments WHERE id = 'legacy-file'"
        )).scalar_one()
    assert content_type['nullable'] is False
    assert legacy_type == 'application/octet-stream'
    assert revision(database) == '20260918_0005'
    database.dispose()


def test_concurrent_upgrade_is_serialized():
    reset_database()
    environment = {**os.environ, 'DATABASE_URL': DATABASE_URL}

    processes = [
        subprocess.Popen(
            [sys.executable, '-m', 'app.init_db'],
            cwd=str(Path(__file__).resolve().parents[1]),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    results = [process.communicate(timeout=30) for process in processes]

    assert [process.returncode for process in processes] == [0, 0]
    assert all('Traceback' not in stderr for _, stderr in results)
    database = create_engine(DATABASE_URL)
    assert revision(database) == '20260918_0005'
    assert 'notes' in inspect(database).get_table_names()
    database.dispose()


def test_notification_migration_adds_preferences_schedule_and_delivery_keys():
    reset_database()
    upgrade_database(DATABASE_URL)
    database = create_engine(DATABASE_URL)

    user_columns = {column['name']: column for column in inspect(database).get_columns('users')}
    note_columns = {column['name']: column for column in inspect(database).get_columns('notes')}
    delivery_columns = {
        column['name']: column
        for column in inspect(database).get_columns('notification_deliveries')
    }
    delivery_uniques = inspect(database).get_unique_constraints('notification_deliveries')

    assert user_columns['reminders_enabled']['nullable'] is False
    assert user_columns['digest_enabled']['nullable'] is False
    assert user_columns['reminder_lead_minutes']['nullable'] is False
    assert note_columns['scheduled_at']['nullable'] is True
    assert note_columns['scheduled_at']['type'].timezone is True
    assert delivery_columns['delivery_key']['nullable'] is False
    assert any(item['column_names'] == ['delivery_key'] for item in delivery_uniques)
    assert revision(database) == '20260918_0005'
    database.dispose()
