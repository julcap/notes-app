from pathlib import Path
import os

from alembic import command
from alembic.config import Config


BACKEND_DIR = Path(__file__).resolve().parents[1]


def upgrade_database(database_url=None):
    config = Config(str(BACKEND_DIR / 'alembic.ini'))
    config.set_main_option('script_location', str(BACKEND_DIR / 'migrations'))
    config.set_main_option('sqlalchemy.url', database_url or os.environ['DATABASE_URL'])
    command.upgrade(config, 'head')
