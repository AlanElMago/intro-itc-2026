import logging
import os
from pathlib import Path
from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware

LOGS_DIR: Final[str] = os.fspath(Path(__file__).parent / 'logs')

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
    'filters': {
        'exclude_paths': {
            '()': 'mylogging.ExcludePaths',
            'paths': ['/health', '/notify', '/predecessor', '/logs'],
        },
    },
    'handlers': {
        'uvicorn': {
            'class':     'logging.FileHandler',
            'formatter': 'default',
            'filename':  f'{LOGS_DIR}/uvicorn.log',
            'mode':      'a',
        },
        'chord.access': {
            'class':     'logging.FileHandler',
            'formatter': 'access',
            'filters':   ['exclude_paths'],
            'filename':  f'{LOGS_DIR}/chord_access.log',
            'mode':      'a',
        },
        'chord.app': {
            'class':     'logging.FileHandler',
            'formatter': 'default',
            'filename':  f'{LOGS_DIR}/chord_app.log',
            'mode':      'a',
        },
        'api.access': {
            'class':     'logging.FileHandler',
            'formatter': 'access',
            'filters':   ['exclude_paths'],
            'filename':  f'{LOGS_DIR}/api_access.log',
            'mode':      'a',
        },
        'api.app': {
            'class':     'logging.FileHandler',
            'formatter': 'default',
            'filename':  f'{LOGS_DIR}/api_app.log',
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
        'chord': {
            'level':     'INFO',
            'handlers':  ['chord.app'],
            'propagate': False,
            'qualname':  'chord',
        },
        'chord.access': {
            'level':     'INFO',
            'handlers':  ['chord.access'],
            'propagate': False,
            'qualname':  'chord.access',
        },
        'chord.error': {
            'level':     'WARNING',
            'handlers':  ['chord.app'],
            'propagate': False,
            'qualname':  'chord.error',
        },
        'api': {
            'level':     'INFO',
            'handlers':  ['api.app'],
            'propagate': False,
            'qualname':  'api',
        },
        'api.access': {
            'level':     'INFO',
            'handlers':  ['api.access'],
            'propagate': False,
            'qualname':  'api.access',
        },
        'api.error': {
            'level':     'WARNING',
            'handlers':  ['api.app'],
            'propagate': False,
            'qualname':  'api.error',
        },
    },
}




class AccessLog(BaseHTTPMiddleware):
    def __init__(self, app, log: logging.Logger):
        super().__init__(app)
        self.log = log

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        client   = f'{request.client.host}:{request.client.port}' \
                   if request.client else '-'

        self.log.info('%s - "%s %s" %d',
            client, request.method, request.url.path, response.status_code,
            extra={'path': request.url.path})

        return response

class ExcludePaths(logging.Filter):
    def __init__(self, paths: list[str]):
        super().__init__()
        self.paths = set(paths)

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, 'path', None) not in self.paths
