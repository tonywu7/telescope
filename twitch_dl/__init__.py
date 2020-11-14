def _config_logging(level=20):
    from logging.config import dictConfig
    from .logger import make_logging_config
    dictConfig(make_logging_config('twitch_dl', level=level))
