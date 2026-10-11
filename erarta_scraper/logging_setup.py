from __future__ import annotations

import logging
import sys

LOGGER_NAME = "erarta"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
