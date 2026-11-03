config = {
    'version': 1,
    'disable_existing_loggers': True,
    'root': {'level': 'INFO', 'handlers': []},
    'formatters': {
        'access': {
            'format': '%(message)s',
            'class': 'logging.Formatter',
        },
        'default': {
            'format': '%(asctime)s %(levelname)-8s %(name)s.%(funcName)s %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
            'class': 'logging.Formatter',
        },
    },
    'handlers': {
        'access': {
            'class': 'logging.FileHandler',
            'formatter': 'access',
            'filename': 'logs/access.log',
            'mode': 'a',
        },
        'app': {
            'class': 'logging.FileHandler',
            'formatter': 'default',
            'filename': 'logs/app.log',
            'mode': 'a',
        },
    },
    'loggers': {
        'uvicorn': {
            'level': 'DEBUG',
            'handlers': ['app'],
            'propagate': False,
        },
        'uvicorn.access': {
            'level': 'INFO',
            'handlers': ['access'],
            'propagate': False,
            'qualname': 'uvicorn.access',
        },
        'uvicorn.error': {
            'level': 'WARNING',
            'handlers': ['app'],
            'propagate': False,
            'qualname': 'uvicorn.error',
        },
        'uvicorn.main': {
            'level': 'DEBUG',
            'handlers': ['app'],
            'propagate': False,
            'qualname': 'uvicorn.main',
        },
    },
}
