"""Track Claude Code usage by reading local data files.

Claude Code stores data in ~/.claude/:
  - projects/<path>/<session-id>.jsonl : per-message token usage (live data!)
  - stats-cache.json                   : daily aggregates (may be stale)
  - history.jsonl                      : user message timestamps
  - sessions/*.json                    : active session PIDs

Plan auto-detection uses `claude auth status` which returns the account's
subscriptionType (free, pro, max, team, enterprise).
"""

import json
import os
import subprocess
from pathlib import Path
from datetime import datetime, timedelta, timezone

from ..config import Config
from ..constants import PlanType, PLAN_LIMITS
from ..utils import now_utc

# Map `claude auth status` subscriptionType -> our PlanType
_SUBSCRIPTION_MAP = {
    "free": PlanType.FREE,
    "pro": PlanType.PRO,
    "max": PlanType.MAX_20X,  # Default Max to 20x; user can override to 5x
    "team": PlanType.TEAM,
    "enterprise": PlanType.ENTERPRISE,
}


def detect_plan() -> dict | None:
    """Run `claude auth status` and return account info.

    Returns dict with keys: loggedIn, subscriptionType, email, orgName, etc.
    Returns None if the command fails.
    """
    try:
        result = subprocess.run(
            ["claude", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError):
        pass
    return None


def detect_plan_type() -> PlanType | None:
    """Auto-detect the user's plan from their Claude Code auth."""
    info = detect_plan()
    if info and info.get("loggedIn"):
        sub = info.get("subscriptionType", "").lower()
        return _SUBSCRIPTION_MAP.get(sub)
    return None


class ClaudeCodeTracker:
    def __init__(self, config: Config):
        self.config = config
        self._usage_cache = None
        self._cache_time = None

    @property
    def claude_dir(self) -> Path:
        return self.config.claude_dir

    # ── Live session token counting ───────────────────────────────────

    def _parse_timestamp(self, ts) -> datetime | None:
        """Parse a timestamp that may be int (ms epoch) or ISO string."""
        if ts is None:
            return None
        try:
            if isinstance(ts, (int, float)):
                return datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
            if isinstance(ts, str):
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError, OSError):
            pass
        return None

    def _scan_session_jsonl_files(self, since: datetime) -> dict:
        """Scan all session JSONL files for token usage within a time window.

        This reads the actual per-message usage data that Claude Code writes
        to ~/.claude/projects/<project>/<session>.jsonl files. Each assistant
        message contains an exact token count from the API response.

        Returns dict with output_tokens, input_tokens, cache_read, messages.
        """
        projects_dir = self.claude_dir / "projects"
        if not projects_dir.exists():
            return {"output_tokens": 0, "input_tokens": 0, "cache_read": 0, "messages": 0}

        total_output = 0
        total_input = 0
        total_cache_read = 0
        msg_count = 0

        for jsonl_path in projects_dir.glob("**/*.jsonl"):
            # Skip very old files (modified before the window)
            try:
                mtime = datetime.fromtimestamp(
                    jsonl_path.stat().st_mtime, tz=timezone.utc
                )
                if mtime < since:
                    continue
            except OSError:
                continue

            try:
                with open(jsonl_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if entry.get("type") != "assistant":
                            continue

                        ts = self._parse_timestamp(entry.get("timestamp"))
                        if ts is None or ts < since:
                            continue

                        usage = entry.get("message", {}).get("usage", {})
                        if usage:
                            total_output += usage.get("output_tokens", 0)
                            total_input += usage.get("input_tokens", 0)
                            total_cache_read += usage.get(
                                "cache_read_input_tokens", 0
                            )
                            msg_count += 1
            except OSError:
                continue

        return {
            "output_tokens": total_output,
            "input_tokens": total_input,
            "cache_read": total_cache_read,
            "messages": msg_count,
        }

    # ── Window usage (primary metric) ─────────────────────────────────

    def get_window_usage(self) -> dict:
        """Get actual token usage within the current rate-limit window.

        Reads session JSONL files for real per-message token counts.
        Uses a short cache to avoid re-scanning on rapid refreshes.
        """
        plan = PLAN_LIMITS.get(self.config.plan_type)
        window_hours = plan.window_hours if plan else 5
        token_limit = self.config.token_limit

        # Short cache (5 seconds) to avoid hammering disk on rapid refreshes
        now = now_utc()
        if (
            self._usage_cache
            and self._cache_time
            and (now - self._cache_time).total_seconds() < 5
        ):
            live = self._usage_cache
        else:
            window_start = now - timedelta(hours=window_hours)
            live = self._scan_session_jsonl_files(window_start)
            self._usage_cache = live
            self._cache_time = now

        output_tokens = live["output_tokens"]
        pct = min(100.0, (output_tokens / token_limit * 100)) if token_limit > 0 else 0

        return {
            "percentage": round(pct, 1),
            "tokens_used": output_tokens,
            "tokens_limit": token_limit,
            "input_tokens": live["input_tokens"],
            "cache_read_tokens": live["cache_read"],
            "window_hours": window_hours,
            "window_messages": live["messages"],
        }

    # ── Today's usage ─────────────────────────────────────────────────

    def get_today_usage(self) -> dict:
        """Get token usage for today from session JSONL files."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        live = self._scan_session_jsonl_files(today_start)

        # Also check stats-cache for message/tool counts
        stats = self._read_stats_cache()
        today_str = datetime.now().strftime("%Y-%m-%d")
        messages = live["messages"]
        tool_calls = 0
        for entry in stats.get("dailyActivity", []):
            if entry.get("date") == today_str:
                tool_calls = entry.get("toolCallCount", 0)
                # Use the larger of live count vs stats count for messages
                messages = max(messages, entry.get("messageCount", 0))

        return {
            "tokens": live["output_tokens"],
            "messages": messages,
            "tool_calls": tool_calls,
        }

    # ── Reset estimation ──────────────────────────────────────────────

    def get_reset_estimate(self) -> dict:
        """Estimate when the oldest tokens in the window expire."""
        plan = PLAN_LIMITS.get(self.config.plan_type)
        window_hours = plan.window_hours if plan else 5

        # If user manually marked a rate limit, use that
        last_hit = self.config.get("last_rate_limit_hit")
        if last_hit:
            try:
                hit_time = datetime.fromisoformat(last_hit)
                if hit_time.tzinfo is None:
                    hit_time = hit_time.replace(tzinfo=timezone.utc)
                reset_time = hit_time + timedelta(hours=window_hours)
                remaining = (reset_time - now_utc()).total_seconds() / 60
                if remaining > 0:
                    return {
                        "reset_time": reset_time.isoformat(),
                        "minutes_remaining": round(remaining),
                        "source": "manual",
                    }
                self.config.set("last_rate_limit_hit", None)
            except (ValueError, TypeError):
                pass

        # Find the oldest assistant message in the window from session files
        window_start = now_utc() - timedelta(hours=window_hours)
        oldest_in_window = self._find_oldest_message_in_window(window_start)

        if oldest_in_window:
            reset_time = oldest_in_window + timedelta(hours=window_hours)
            remaining = (reset_time - now_utc()).total_seconds() / 60
            return {
                "reset_time": reset_time.isoformat(),
                "minutes_remaining": max(0, round(remaining)),
                "source": "estimated",
            }

        return {
            "reset_time": None,
            "minutes_remaining": None,
            "source": "none",
        }

    def _find_oldest_message_in_window(self, window_start: datetime) -> datetime | None:
        """Find the timestamp of the oldest assistant message in the window."""
        projects_dir = self.claude_dir / "projects"
        if not projects_dir.exists():
            return None

        oldest = None
        for jsonl_path in projects_dir.glob("**/*.jsonl"):
            try:
                mtime = datetime.fromtimestamp(
                    jsonl_path.stat().st_mtime, tz=timezone.utc
                )
                if mtime < window_start:
                    continue
            except OSError:
                continue

            try:
                with open(jsonl_path) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if entry.get("type") != "assistant":
                            continue
                        ts = self._parse_timestamp(entry.get("timestamp"))
                        if ts and ts >= window_start:
                            if oldest is None or ts < oldest:
                                oldest = ts
                            break  # First match in file is likely oldest
            except OSError:
                continue

        return oldest

    # ── Active sessions ───────────────────────────────────────────────

    def get_active_sessions(self) -> list[dict]:
        sessions_dir = self.claude_dir / "sessions"
        if not sessions_dir.exists():
            return []

        active = []
        for f in sessions_dir.glob("*.json"):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                pid = data.get("pid")
                if pid and self._is_running(pid):
                    active.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        return active

    @staticmethod
    def _is_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    # ── Lifetime history (from stats-cache) ───────────────────────────

    def _read_stats_cache(self) -> dict:
        path = self.claude_dir / "stats-cache.json"
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def get_history_summary(self) -> dict:
        stats = self._read_stats_cache()
        model_usage = stats.get("modelUsage", {})

        total_input = sum(m.get("inputTokens", 0) for m in model_usage.values())
        total_output = sum(m.get("outputTokens", 0) for m in model_usage.values())
        total_cache = sum(
            m.get("cacheReadInputTokens", 0) for m in model_usage.values()
        )

        return {
            "total_sessions": stats.get("totalSessions", 0),
            "total_messages": stats.get("totalMessages", 0),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cache_tokens": total_cache,
            "models_used": list(model_usage.keys()),
            "first_session": stats.get("firstSessionDate"),
        }

    def get_daily_usage(self, days: int = 7) -> list[dict]:
        """Token usage per day for the last N days."""
        stats = self._read_stats_cache()
        daily_tokens = stats.get("dailyModelTokens", [])
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        result = []
        for entry in daily_tokens:
            if entry.get("date", "") >= cutoff:
                total = sum(entry.get("tokensByModel", {}).values())
                result.append({"date": entry["date"], "tokens": total})
        return result

    def get_model_breakdown(self) -> dict[str, dict]:
        """Per-model token usage from lifetime stats."""
        stats = self._read_stats_cache()
        return stats.get("modelUsage", {})
