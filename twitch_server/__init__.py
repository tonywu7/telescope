def _config_logging(*args, **kwargs):
    from logging.config import dictConfig

    from .logger import make_logging_config
    dictConfig(make_logging_config('twitch_server', *args, **kwargs))
