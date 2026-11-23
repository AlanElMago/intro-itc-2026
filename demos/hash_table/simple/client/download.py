import argparse
import sys
import time
from pathlib import Path
from typing import Final
from urllib.parse import quote

import httpx
from common import CLIENT_DIR, HASH_TABLE_URL, log

DOWNLOADS_DIR: Final[Path] = CLIENT_DIR / 'downloads'


def main() -> int:
    parser = argparse.ArgumentParser(description='Download a file from the hash_table service.')
    parser.add_argument('filename', help=f'name of the file to download into {DOWNLOADS_DIR}')
    args = parser.parse_args()

    if Path(args.filename).name != args.filename or args.filename in ('', '.', '..'):
        parser.error(f'{args.filename!r} must be a plain filename')

    try:
        start = time.perf_counter()
        response = httpx.get(f'{HASH_TABLE_URL}/files/{quote(args.filename)}')
        elapsed = time.perf_counter() - start
    except httpx.HTTPError as e:
        log.error(f'could not reach {HASH_TABLE_URL}: {e}')
        return 1

    storage = response.headers.get('X-Storage', 'unknown')

    log.info(
        f'download {args.filename} (storage={storage}, size={len(response.content)} B) '
        f'-> {response.status_code} in {elapsed * 1e3:.2f} ms'
    )

    if not response.is_success:
        print(response.text, file=sys.stderr)
        return 1

    DOWNLOADS_DIR.mkdir(exist_ok=True)
    path = DOWNLOADS_DIR / args.filename
    path.write_bytes(response.content)
    print(f'saved to {path}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
