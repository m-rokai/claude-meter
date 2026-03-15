"""Track Anthropic API usage via response headers.

When users make API calls, the response includes rate-limit headers:
  x-ratelimit-limit-requests
  x-ratelimit-limit-tokens
  x-ratelimit-remaining-requests
  x-ratelimit-remaining-tokens
  x-ratelimit-reset-requests
  x-ratelimit-reset-tokens

This tracker can ingest those headers (e.g. from a logging proxy or manual input)
and display the current API rate-limit state.
"""

import json
from pathlib import Path
from datetime import datetime, timezone

from ..config import Config

API_USAGE_FILE = Path.home() / ".claude-meter" / "api_usage.json"


class APITracker:
    """Tracks API usage from logged rate-limit headers."""

    def __init__(self, config: Config):
        self.config = config
        self._state = self._load()

    def _load(self) -> dict:
        if API_USAGE_FILE.exists():
            try:
                with open(API_USAGE_FILE) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save(self):
        API_USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(API_USAGE_FILE, "w") as f:
            json.dump(self._state, f, indent=2)

    def ingest_headers(self, headers: dict):
        """Parse Anthropic API response headers and store rate-limit state."""
        self._state = {
            "limit_requests": _int(headers.get("x-ratelimit-limit-requests")),
            "limit_tokens": _int(headers.get("x-ratelimit-limit-tokens")),
            "remaining_requests": _int(
                headers.get("x-ratelimit-remaining-requests")
            ),
            "remaining_tokens": _int(headers.get("x-ratelimit-remaining-tokens")),
            "reset_requests": headers.get("x-ratelimit-reset-requests"),
            "reset_tokens": headers.get("x-ratelimit-reset-tokens"),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    def get_state(self) -> dict:
        """Current API rate-limit state."""
        if not self._state:
            return {"active": False}

        limit_tk = self._state.get("limit_tokens", 0)
        remaining_tk = self._state.get("remaining_tokens", 0)
        used_tk = limit_tk - remaining_tk if limit_tk else 0
        pct = (used_tk / limit_tk * 100) if limit_tk else 0

        return {
            "active": True,
            "percentage": round(pct, 1),
            "tokens_used": used_tk,
            "tokens_remaining": remaining_tk,
            "tokens_limit": limit_tk,
            "requests_remaining": self._state.get("remaining_requests"),
            "requests_limit": self._state.get("limit_requests"),
            "reset_tokens": self._state.get("reset_tokens"),
            "reset_requests": self._state.get("reset_requests"),
            "recorded_at": self._state.get("recorded_at"),
        }

    def clear(self):
        self._state = {}
        self._save()


def _int(val) -> int:
    if val is None:
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0
