import argparse
import sys
import time
from pathlib import Path
from typing import Final

import httpx
from common import CLIENT_DIR, HASH_TABLE_URL, log

FILES_DIR: Final[Path] = CLIENT_DIR / 'files'


def main() -> int:
    parser = argparse.ArgumentParser(description='Upload a file to the hash_table service.')
    parser.add_argument('filename', help=f'name of a file in {FILES_DIR}')
    parser.add_argument(
        '--storage',
        choices=['ram', 'disk', 'cloud'],
        default='ram',
        help='where the service should store the file (default: ram)'
    )
    args = parser.parse_args()

    path = FILES_DIR / args.filename

    if Path(args.filename).name != args.filename or not path.is_file():
        parser.error(f'{args.filename!r} is not a file in {FILES_DIR}')

    try:
        with path.open('rb') as f:
            start = time.perf_counter()
            response = httpx.post(
                f'{HASH_TABLE_URL}/files',
                params={'storage': args.storage},
                files={'file': (path.name, f, 'application/octet-stream')}
            )
            elapsed = time.perf_counter() - start
    except httpx.HTTPError as e:
        log.error(f'could not reach {HASH_TABLE_URL}: {e}')
        return 1

    log.info(
        f'upload {path.name} (storage={args.storage}, size={path.stat().st_size} B) '
        f'-> {response.status_code} in {elapsed * 1e3:.2f} ms'
    )
    print(response.text)

    return 0 if response.is_success else 1


if __name__ == '__main__':
    sys.exit(main())
