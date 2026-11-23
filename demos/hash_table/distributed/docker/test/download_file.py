import argparse
from pathlib import Path

import httpx

DOWNLOADS_DIR = Path(__file__).parent / 'downloads'


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Download a file from the Chord network.'
    )
    parser.add_argument('filename')
    parser.add_argument('--node',
        default = 'localhost:42000',
        help    = 'address of any Chord node (default: %(default)s)'
    )
    args = parser.parse_args()

    with httpx.Client(timeout=5.0) as client:
        res = client.get(f'http://{args.node}/key/by-filename/{args.filename}')
        res.raise_for_status()
        location: str = res.json()['address']
        print(f'{args.filename} is located at {location}')

        port = location.rsplit(':', 1)[1]
        host = f'localhost:{port}'

        DOWNLOADS_DIR.mkdir(exist_ok=True)

        dest = DOWNLOADS_DIR / Path(args.filename).name
        url  = f'http://{host}/file/{args.filename}'

        with client.stream('GET', url) as file_res:
            file_res.raise_for_status()
            with open(dest, 'wb') as f:
                f.writelines(file_res.iter_bytes())

    print(f'saved to {dest}')


if __name__ == '__main__':
    main()
