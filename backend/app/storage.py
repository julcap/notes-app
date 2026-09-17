import os
from pathlib import Path

STORAGE = Path(os.getenv('UPLOAD_DIR', '/data/uploads'))
MAX_FILE_SIZE = 20 * 1024 * 1024
