"""Logging configuration.

Dev: human-readable single-line logs.
Prod: JSON logs — one object per line, machine-parseable, so a log aggregator
(Azure Monitor, CloudWatch, Loki) can index fields instead of grepping text.

Stdlib logging is used deliberately: no extra dependency, and every library in
our stack (uvicorn, sqlalchemy, httpx) already emits through it, so one
dictConfig governs everything.
"""

import json
import logging
import logging.config
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str, environment: str) -> None:
    formatter = (
        {"()": JsonFormatter}
        if environment == "prod"
        else {"format": "%(asctime)s %(levelname)-8s %(name)s — %(message)s"}
    )
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"default": formatter},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {"level": level.upper(), "handlers": ["console"]},
            "loggers": {
                # uvicorn installs its own handlers; route through ours instead
                "uvicorn": {"handlers": ["console"], "propagate": False},
                "uvicorn.access": {"handlers": ["console"], "propagate": False},
            },
        }
    )
