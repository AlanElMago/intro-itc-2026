import logging
from typing import Final

CONFIG: Final[dict] = {
    'version': 1,
    'disable_existing_loggers': True,
    'root': {'level': 'INFO', 'handlers': [] },
    'formatters': {
        'access': {
            'format': '%(message)s',
            'class':  'logging.Formatter',
        },
        'default': {
            'format':  '%(asctime)s %(levelname)-8s %(name)s.%(funcName)s %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
            'class':   'logging.Formatter',
        },
    },
    'handlers': {
        'uvicorn': {
            'class':     'logging.FileHandler',
            'formatter': 'default',
            'filename':  'logs/uvicorn.log',
            'mode':      'a',
        },
        'uvicorn.access': {
            'class':     'logging.FileHandler',
            'formatter': 'access',
            'filename':  'logs/access.log',
            'mode':      'a',
        },
    },
    'loggers': {
        'uvicorn': {
            'level':     'INFO',
            'handlers':  ['uvicorn'],
            'propagate': False,
            'qualname':  'uvicorn',
        },
        'uvicorn.access': {
            'level':     'INFO',
            'handlers':  ['uvicorn.access'],
            'propagate': False,
            'qualname':  'uvicorn.access',
        },
        'uvicorn.error': {
            'level':     'INFO',
            'handlers':  ['uvicorn'],
            'propagate': False,
            'qualname':  'uvicorn.error',
        },
    }
}




class PathsFilter(logging.Filter):
    def __init__(self, name: str="", paths: list[str] | None=None) -> None:
        super().__init__(name)
        self.paths = paths

    def filter(self, record: logging.LogRecord) -> bool:
        if self.paths is None:
            return True

        if isinstance(record.args, tuple) and len(record.args) >= 3:
            request_path = str(record.args[2])

            for path in self.paths:
                if request_path.startswith(path):
                    return False

        return True
