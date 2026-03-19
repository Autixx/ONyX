from __future__ import annotations

import logging
from pathlib import Path

from .paths import LOG_DIR, ensure_runtime_dirs


_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str) -> logging.Logger:
    ensure_runtime_dirs()
    logger = _LOGGERS.get(name)
    if logger is not None:
        return logger
    logger = logging.getLogger(f"onyx-client.{name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    log_path = Path(LOG_DIR) / "daemon.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s.%(msecs)03d %(process)d %(name)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    logger.handlers.clear()
    logger.addHandler(handler)
    _LOGGERS[name] = logger
    return logger


def short_text(value: str, limit: int = 800) -> str:
    text = (value or "").strip().replace("\r", "\\r").replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
