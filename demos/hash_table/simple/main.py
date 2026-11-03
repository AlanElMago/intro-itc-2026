import os
import pathlib

from hashtable import Storage

INPUT_DIRNAME  = 'input'
OUTPUT_DIRNAME = 'output'


storage = Storage()

input_dir = pathlib.Path(INPUT_DIRNAME)
filenames = [f.name for f in input_dir.iterdir() if f.is_file()]

print('\nWriting to storage...\n')

for filename in filenames:
    with open(file=os.path.join(INPUT_DIRNAME, filename), mode='rb') as f:
        storage.write(filename, f.read())

print('\nReading from storage...\n')

for filename in filenames:
    data = storage.read(filename)

    if data:
        with open(file=os.path.join(OUTPUT_DIRNAME, filename), mode='wb') as f:
            f.write(data)
