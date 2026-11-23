import logging
import os
from pathlib import Path
from typing import Final

CLIENT_DIR: Final[Path] = Path(__file__).resolve().parent
HASH_TABLE_URL: Final[str] = os.environ.get('HASH_TABLE_URL', 'http://localhost:8000').rstrip('/')
LOG_DIR: Final[Path] = CLIENT_DIR / 'logs'

LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level    = logging.INFO,
    format   = '%(asctime)s %(levelname)-8s  %(message)s',
    handlers = [
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / 'client.log'),
    ]
)
# httpx logs every request at INFO; keep the log to our own timing lines.
logging.getLogger('httpx').setLevel(logging.WARNING)

log = logging.getLogger('client')
