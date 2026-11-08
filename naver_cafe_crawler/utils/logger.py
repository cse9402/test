"""로깅 설정. 쿠키·토큰 값이 로그에 남지 않도록 마스킹 필터 적용."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_SENSITIVE = [
    re.compile(r"(NID_AUT|NID_SES|NID_JKL|nid_inf)\s*[=:]\s*[^;\s,'\"]+", re.I),
    re.compile(r"(cookie|authorization|password|passwd|pw)\s*[=:]\s*[^;\s,'\"]+", re.I),
]


def mask_sensitive(text: str) -> str:
    for pat in _SENSITIVE:
        text = pat.sub(lambda m: f"{m.group(1)}=***", text)
    return text


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = mask_sensitive(str(record.msg))
        if record.args:
            record.args = tuple(mask_sensitive(str(a)) for a in record.args) \
                if isinstance(record.args, tuple) else record.args
        return True


def setup_logging(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("cafe_crawler")
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler = RotatingFileHandler(log_dir / "crawler.log", maxBytes=5_000_000,
                                       backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    for h in (file_handler, stream):
        h.addFilter(SensitiveDataFilter())
        logger.addHandler(h)
    return logger


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger("cafe_crawler" + (f".{name}" if name else ""))
