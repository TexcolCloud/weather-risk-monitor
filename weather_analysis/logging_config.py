"""Application logging configuration."""

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "weather-analysis.log"
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(console: bool = False) -> logging.Logger:
    """Configure UTF-8 rotating application logs exactly once per process."""
    logger = logging.getLogger("weather_analysis")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not any(getattr(handler, "_weather_analysis_handler", False) for handler in logger.handlers):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            LOG_FILE,
            when="midnight",
            backupCount=30,
            encoding="utf-8",
        )
        file_handler._weather_analysis_handler = True
        file_handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(file_handler)

    if console and not any(getattr(handler, "_weather_analysis_console", False) for handler in logger.handlers):
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler._weather_analysis_handler = True
        console_handler._weather_analysis_console = True
        console_handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(console_handler)
    return logger
