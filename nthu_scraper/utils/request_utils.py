"""Utilities for configuring outgoing HTTP requests."""

from __future__ import annotations

import random
from functools import lru_cache
from typing import Dict

# A small pool of modern desktop and mobile browsers to mimic real usage.
_USER_AGENT_POOL = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/118.0.5993.90 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
)


def _choose_user_agent() -> str:
    """Pick a realistic UA string for this crawler run."""
    return random.choice(_USER_AGENT_POOL)


@lru_cache(maxsize=1)
def get_default_user_agent() -> str:
    """Return the cached UA value so every spider advertises the same client."""
    return _choose_user_agent()


def get_default_headers() -> Dict[str, str]:
    """Build shared request headers we want every spider to reuse."""
    return {"User-Agent": get_default_user_agent()}
