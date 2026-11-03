import os

from hashtable import Storage

INPUT_DIRNAME  = 'input'
OUTPUT_DIRNAME = 'output'
FILENAME       = 'landscape.jpg'


storage = Storage()

with open(file=os.path.join(INPUT_DIRNAME, FILENAME), mode='rb') as f:
    storage.write(FILENAME, f.read())

with open(file=os.path.join(INPUT_DIRNAME, FILENAME), mode='rb') as f:
    storage.write(FILENAME, f.read())

data = storage.read(FILENAME)

if data:
    with open(file=os.path.join(OUTPUT_DIRNAME, FILENAME), mode='wb') as f:
        f.write(data)
