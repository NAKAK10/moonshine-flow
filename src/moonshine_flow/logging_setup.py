"""Logging helpers for moonshine-flow."""

from __future__ import annotations

import logging


def configure_logging(level: str) -> None:
    """Configure project logging once."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
