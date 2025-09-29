from __future__ import annotations
import logging
import re

COOKIE_RE = re.compile(r"(li_at=)([^; \n]+)", re.IGNORECASE)
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")

class PIIMask(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = COOKIE_RE.sub(r"\1***", record.msg)
            msg = EMAIL_RE.sub(r"\1@***", msg)
            record.msg = msg
        if record.args:
            if isinstance(record.args, tuple):
                args = []
                for a in record.args:
                    if isinstance(a, str):
                        a = COOKIE_RE.sub(r"\1***", a)
                        a = EMAIL_RE.sub(r"\1@***", a)
                    args.append(a)
                record.args = tuple(args)
        return True

def setup_logger(level: str = "INFO", json_mode: bool = False) -> logging.Logger:
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    # clear handlers
    for h in list(logger.handlers):
        logger.removeHandler(h)

    h = logging.StreamHandler()
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    if json_mode:
        fmt = '{"ts":"%(asctime)s","lvl":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'
    f = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")
    h.setFormatter(f)
    h.addFilter(PIIMask())
    logger.addHandler(h)

    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("selenium").setLevel(logging.ERROR)
    return logger
