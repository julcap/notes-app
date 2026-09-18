import os
from collections.abc import Iterable
from pathlib import Path

STORAGE = Path(os.getenv('UPLOAD_DIR', '/data/uploads'))
MAX_FILE_SIZE = 20 * 1024 * 1024
FILE_CLEANUP_LOCK_ID = 538_719_443

QuarantinedFile = tuple[Path, Path]


def quarantine_files(ids: Iterable[str], root: Path = STORAGE) -> list[QuarantinedFile]:
    trash = root / '.trash'
    trash.mkdir(parents=True, exist_ok=True)
    quarantined: list[QuarantinedFile] = []
    try:
        for item_id in ids:
            source = root / item_id
            if not source.exists():
                continue
            destination = trash / item_id
            source.replace(destination)
            quarantined.append((source, destination))
    except OSError:
        restore_quarantined(quarantined)
        raise
    return quarantined


def restore_quarantined(quarantined: Iterable[QuarantinedFile]) -> None:
    for source, destination in reversed(list(quarantined)):
        if destination.exists():
            destination.replace(source)


def discard_quarantined(quarantined: Iterable[QuarantinedFile]) -> None:
    for _, destination in quarantined:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
