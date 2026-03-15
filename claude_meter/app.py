"""Claude Meter — macOS menu bar app for tracking Claude AI usage.

Detection methods (tried in order):
  1. `claude auth status` — reads subscriptionType from Claude Code CLI (non-invasive)
  2. API key probe — user pastes key, app makes a minimal API call to read
     x-ratelimit-limit-tokens from response headers (exact limit, no guessing)
  3. Manual — user picks their plan from the Settings menu
"""

import json
import subprocess
import urllib.request
import urllib.error
import rumps

from datetime import datetime, timedelta, timezone
from .config import Config, CONFIG_FILE
from .constants import (
    PlanType,
    PLAN_LIMITS,
    USAGE_LEVELS,
    STATUS_ICONS,
    DEFAULT_THRESHOLDS,
)
from .trackers.claude_code import ClaudeCodeTracker, detect_plan
from .trackers.api_tracker import APITracker
from .notifications import notify
from .utils import format_tokens, format_duration
from .watcher import ClaudeWatcher

PLAN_DISPLAY_ORDER = [
    PlanType.FREE,
    PlanType.PRO,
    PlanType.MAX_5X,
    PlanType.MAX_20X,
    PlanType.TEAM,
    PlanType.ENTERPRISE,
    PlanType.API,
]

# Map `claude auth status` subscriptionType values
_SUB_MAP = {
    "free": PlanType.FREE,
    "pro": PlanType.PRO,
    "max": PlanType.MAX_20X,   # default Max to 20x
    "team": PlanType.TEAM,
    "enterprise": PlanType.ENTERPRISE,
}

# Infer plan from x-ratelimit-limit-tokens header value
_LIMIT_THRESHOLDS = [
    (5_000_000, PlanType.MAX_20X),
    (1_000_000, PlanType.MAX_5X),
    (500_000, PlanType.ENTERPRISE),
    (200_000, PlanType.PRO),
    (0, PlanType.FREE),
]


def _probe_api_key(api_key: str) -> dict | None:
    """Make a minimal API call and return rate-limit headers.

    Uses count_tokens which is free, or falls back to a tiny messages call.
    Returns dict with limit_tokens, remaining_tokens, etc. or None on failure.
    """
    body = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            headers = dict(resp.headers)
            return {
                "limit_tokens": int(headers.get("x-ratelimit-limit-tokens", 0)),
                "remaining_tokens": int(headers.get("x-ratelimit-remaining-tokens", 0)),
                "limit_requests": int(headers.get("x-ratelimit-limit-requests", 0)),
                "remaining_requests": int(headers.get("x-ratelimit-remaining-requests", 0)),
                "reset_tokens": headers.get("x-ratelimit-reset-tokens", ""),
                "reset_requests": headers.get("x-ratelimit-reset-requests", ""),
            }
    except urllib.error.HTTPError as e:
        # Even 4xx/5xx responses include rate-limit headers
        headers = dict(e.headers) if e.headers else {}
        lt = headers.get("x-ratelimit-limit-tokens")
        if lt:
            return {
                "limit_tokens": int(lt),
                "remaining_tokens": int(headers.get("x-ratelimit-remaining-tokens", 0)),
                "limit_requests": int(headers.get("x-ratelimit-limit-requests", 0)),
                "remaining_requests": int(headers.get("x-ratelimit-remaining-requests", 0)),
                "reset_tokens": headers.get("x-ratelimit-reset-tokens", ""),
                "reset_requests": headers.get("x-ratelimit-reset-requests", ""),
            }
    except Exception:
        pass
    return None


def _plan_from_limit(limit_tokens: int) -> PlanType:
    """Map a token limit to the most likely plan."""
    for threshold, plan in _LIMIT_THRESHOLDS:
        if limit_tokens >= threshold:
            return plan
    return PlanType.FREE


# ══════════════════════════════════════════════════════════════════════

class ClaudeMeterApp(rumps.App):
    def __init__(self):
        super().__init__("Claude Meter", title="⚪ --", quit_button=None)
        self.config = Config()
        self.cc_tracker = ClaudeCodeTracker(self.config)
        self.api_tracker = APITracker(self.config)
        self._last_notified_threshold = 0
        self._is_rate_limited = False

        # Silent auto-detect on startup
        self._auto_detect_plan()

        self._build_menu()
        self._refresh(None)

        # File watcher for instant updates
        self._watcher = ClaudeWatcher(self.config.claude_dir, self._on_file_change)
        self._watcher.start()

    # ── Plan detection ────────────────────────────────────────────────

    def _auto_detect_plan(self):
        """Silently detect plan via `claude auth status`. No popups."""
        info = detect_plan()
        if not info or not info.get("loggedIn"):
            return

        sub = info.get("subscriptionType", "").lower()
        detected = _SUB_MAP.get(sub)
        if detected is None:
            return

        email = info.get("email", "")
        self.config.set("_account_email", email)
        self.config.set("_detected_subscription", sub)
        self.config.set("_auth_method", "claude_cli")

        # Only overwrite plan if not manually set
        if not self.config.get("_plan_manually_set"):
            # Preserve specific max tier if user already chose one
            if sub == "max" and self.config.plan_type in (PlanType.MAX_5X, PlanType.MAX_20X):
                return
            self.config.plan_type = detected

    @rumps.timer(300)
    def _periodic_redetect(self, _):
        """Re-detect plan every 5 minutes to catch account changes."""
        if self.config.get("_plan_manually_set"):
            return
        self._auto_detect_plan()

    # ── File watcher ──────────────────────────────────────────────────

    def _on_file_change(self):
        try:
            self._refresh(None)
        except Exception:
            pass

    # ── Menu construction ─────────────────────────────────────────────

    def _build_menu(self):
        self.mi_usage_pct = rumps.MenuItem("Usage: ...")
        self.mi_tokens = rumps.MenuItem("Tokens: ...")
        self.mi_messages = rumps.MenuItem("Messages: ...")
        self.mi_sessions = rumps.MenuItem("Sessions: ...")

        self.mi_reset = rumps.MenuItem("Reset: ...")
        self.mi_window = rumps.MenuItem("Window: ...")

        self.mi_account = rumps.MenuItem("Account: ...")
        self.mi_plan = rumps.MenuItem("Plan: ...")
        self.mi_multiplier = rumps.MenuItem("Multiplier: ...")

        self.mi_total_sessions = rumps.MenuItem("Total sessions: ...")
        self.mi_total_messages = rumps.MenuItem("Total messages: ...")
        self.mi_total_tokens = rumps.MenuItem("Total tokens: ...")
        self.mi_models = rumps.MenuItem("Models: ...")

        self.mi_daily_header = rumps.MenuItem("Last 7 Days")
        self.mi_daily_items = []
        for _ in range(7):
            item = rumps.MenuItem("")
            self.mi_daily_items.append(item)
            self.mi_daily_header.add(item)

        self.mi_rate_limit = rumps.MenuItem(
            "I Got Rate Limited", callback=self._mark_rate_limited
        )
        self.mi_clear_rate_limit = rumps.MenuItem(
            "Clear Rate Limit", callback=self._clear_rate_limit
        )

        # ── Settings ──
        settings = rumps.MenuItem("Settings")

        # Plan
        plan_menu = rumps.MenuItem("Plan")
        for pt in PLAN_DISPLAY_ORDER:
            limits = PLAN_LIMITS.get(pt)
            label = limits.name if limits else pt.value
            check = "✓ " if pt == self.config.plan_type else "   "
            plan_menu.add(
                rumps.MenuItem(
                    f"{check}{label}",
                    callback=lambda s, p=pt: self._set_plan(p),
                )
            )
        settings.add(plan_menu)

        # Multiplier
        mult_menu = rumps.MenuItem("Usage Multiplier (Events)")
        for m in [1.0, 1.5, 2.0, 3.0, 4.0, 5.0]:
            label = f"{m}x"
            if m == 1.0:
                label += " (normal)"
            elif m == 2.0:
                label += " (double usage)"
            mult_menu.add(
                rumps.MenuItem(label, callback=lambda s, v=m: self._set_multiplier(v))
            )
        settings.add(mult_menu)

        # Refresh interval
        interval_menu = rumps.MenuItem("Refresh Interval")
        for secs in [10, 15, 30, 60, 120]:
            interval_menu.add(
                rumps.MenuItem(
                    f"{secs}s", callback=lambda s, v=secs: self._set_refresh(v)
                )
            )
        settings.add(interval_menu)

        settings.add(None)
        settings.add(rumps.MenuItem("Enter API Key...", callback=self._enter_api_key))
        settings.add(rumps.MenuItem("Re-detect Plan", callback=self._redetect_plan))
        settings.add(rumps.MenuItem("Open Config File", callback=self._open_config))

        # ── Assemble ──
        self.menu = [
            self.mi_usage_pct,
            self.mi_tokens,
            self.mi_messages,
            self.mi_sessions,
            None,
            self.mi_reset,
            self.mi_window,
            None,
            self.mi_account,
            self.mi_plan,
            self.mi_multiplier,
            None,
            self.mi_total_sessions,
            self.mi_total_messages,
            self.mi_total_tokens,
            self.mi_models,
            None,
            self.mi_daily_header,
            None,
            self.mi_rate_limit,
            self.mi_clear_rate_limit,
            None,
            rumps.MenuItem("Refresh Now", callback=self._refresh),
            settings,
            None,
            rumps.MenuItem("Quit Claude Meter", callback=self._quit),
        ]

    # ── Periodic refresh ──────────────────────────────────────────────

    @rumps.timer(30)
    def _refresh(self, _):
        try:
            self._do_refresh()
        except Exception as e:
            self.title = "⚪ ERR"
            print(f"[claude-meter] refresh error: {e}", flush=True)

    def _do_refresh(self):
        window = self.cc_tracker.get_window_usage()
        today = self.cc_tracker.get_today_usage()
        sessions = self.cc_tracker.get_active_sessions()
        reset = self.cc_tracker.get_reset_estimate()
        history = self.cc_tracker.get_history_summary()
        plan = PLAN_LIMITS.get(self.config.plan_type)
        daily = self.cc_tracker.get_daily_usage(7)

        pct = window["percentage"]
        level = self._level(pct)

        self._check_rate_limit_expired(plan)

        icon = STATUS_ICONS.get(
            "rate_limited" if self._is_rate_limited else level, "⚪"
        )
        self.title = f"{icon} {pct:.0f}%"

        # Usage
        self.mi_usage_pct.title = f"Usage: {pct:.1f}%"
        self.mi_tokens.title = (
            f"Tokens: {format_tokens(window['tokens_used'])} "
            f"/ {format_tokens(window['tokens_limit'])}"
        )
        self.mi_messages.title = f"Messages today: {today['messages']:,}"
        self.mi_sessions.title = f"Active sessions: {len(sessions)}"

        # Reset
        mins = reset.get("minutes_remaining")
        if self._is_rate_limited and mins is not None and mins > 0:
            self.mi_reset.title = f"Rate limited — resets in {format_duration(mins)}"
        elif mins is not None and mins > 0:
            self.mi_reset.title = f"Window resets in ~{format_duration(mins)}"
        else:
            self.mi_reset.title = "Reset: rolling window (idle)"
        window_h = window.get("window_hours", 5)
        self.mi_window.title = (
            f"Window: {window_h}h | {window['window_messages']} msgs in window"
        )

        # Account & Plan
        email = self.config.get("_account_email", "")
        auth = self.config.get("_auth_method", "")
        if email:
            self.mi_account.title = f"Account: {email}"
        elif auth == "api_key":
            self.mi_account.title = "Account: API key"
        else:
            self.mi_account.title = "Account: not connected"
        self.mi_plan.title = f"Plan: {plan.name}" if plan else "Plan: Unknown"
        mult = self.config.usage_multiplier
        self.mi_multiplier.title = f"Multiplier: {mult}x" + (
            " ⚡ BOOSTED" if mult > 1.0 else ""
        )

        # History
        self.mi_total_sessions.title = (
            f"Total sessions: {history['total_sessions']:,}"
        )
        self.mi_total_messages.title = (
            f"Total messages: {history['total_messages']:,}"
        )
        total_tk = history["total_input_tokens"] + history["total_output_tokens"]
        self.mi_total_tokens.title = f"Total tokens: {format_tokens(total_tk)}"
        models = ", ".join(
            m.replace("claude-", "") for m in history.get("models_used", [])
        )
        self.mi_models.title = f"Models: {models}" if models else "Models: —"

        # Daily breakdown
        for i, item in enumerate(self.mi_daily_items):
            if i < len(daily):
                d = daily[-(i + 1)]
                bar = self._bar(d["tokens"], window["tokens_limit"])
                item.title = (
                    f"  {d['date']}  {bar}  {format_tokens(d['tokens'])}"
                )
            else:
                item.title = ""

        self._check_notifications(pct)

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _level(pct: float) -> str:
        for name, (lo, hi) in USAGE_LEVELS.items():
            if lo <= pct < hi:
                return name
        return "critical" if pct >= 95 else "unknown"

    @staticmethod
    def _bar(value: int, limit: int, width: int = 10) -> str:
        if limit <= 0:
            return "░" * width
        filled = min(width, int(value / limit * width))
        return "█" * filled + "░" * (width - filled)

    def _check_rate_limit_expired(self, plan):
        last_hit = self.config.get("last_rate_limit_hit")
        if not last_hit:
            self._is_rate_limited = False
            return
        try:
            hit_time = datetime.fromisoformat(last_hit)
            if hit_time.tzinfo is None:
                hit_time = hit_time.replace(tzinfo=timezone.utc)
            window_h = plan.window_hours if plan else 5
            reset_time = hit_time + timedelta(hours=window_h)
            now = datetime.now(timezone.utc)
            if now >= reset_time:
                self.config.set("last_rate_limit_hit", None)
                self._is_rate_limited = False
                notify("Claude Meter", "Rate limit has reset! You can resume.")
            else:
                self._is_rate_limited = True
        except (ValueError, TypeError):
            self._is_rate_limited = False

    def _check_notifications(self, pct: float):
        thresholds = self.config.get("notification_thresholds", DEFAULT_THRESHOLDS)
        hit = 0
        for t in sorted(thresholds):
            if pct >= t:
                hit = t
        if hit > self._last_notified_threshold:
            if hit >= 95:
                notify(
                    "Claude Usage Critical",
                    f"You've used {pct:.0f}% of your limit!",
                )
            elif hit >= 80:
                notify(
                    "Claude Usage High",
                    f"You've used {pct:.0f}% of your limit.",
                )
            elif hit >= 60:
                notify(
                    "Claude Usage Notice",
                    f"You've used {pct:.0f}% of your limit.",
                )
        self._last_notified_threshold = hit
        if pct < 50:
            self._last_notified_threshold = 0

    # ── User actions ──────────────────────────────────────────────────

    def _mark_rate_limited(self, _):
        self.config.set(
            "last_rate_limit_hit", datetime.now(timezone.utc).isoformat()
        )
        self._is_rate_limited = True
        self._refresh(None)
        plan = PLAN_LIMITS.get(self.config.plan_type)
        window_h = plan.window_hours if plan else 5
        notify(
            "Rate Limit Recorded",
            f"Timer started — resets in ~{window_h}h. We'll notify you.",
        )

    def _clear_rate_limit(self, _):
        self.config.set("last_rate_limit_hit", None)
        self._is_rate_limited = False
        self._refresh(None)

    def _set_plan(self, plan_type: PlanType):
        self.config.plan_type = plan_type
        self.config.set("_plan_manually_set", True)
        plan = PLAN_LIMITS.get(plan_type)
        notify(
            "Plan Updated",
            f"Now tracking: {plan.name}" if plan else str(plan_type),
        )
        self._refresh(None)

    def _set_multiplier(self, value: float):
        self.config.usage_multiplier = value
        msg = f"Multiplier set to {value}x"
        if value > 1.0:
            msg += " — boosted limits active!"
        notify("Multiplier Updated", msg)
        self._refresh(None)

    def _set_refresh(self, secs: int):
        self.config.set("refresh_interval", secs)
        notify("Refresh Interval", f"Now refreshing every {secs}s")

    def _enter_api_key(self, _):
        """Let user paste an API key. Probes actual rate limits from headers."""
        w = rumps.Window(
            title="Enter Anthropic API Key",
            message=(
                "Paste your API key to auto-detect your exact rate limits.\n"
                "The key is stored locally in ~/.claude-meter/config.json.\n"
                "A single minimal API call will be made to read your limits."
            ),
            default_text=self.config.get("api_key", ""),
            ok="Detect Limits",
            cancel="Cancel",
            dimensions=(380, 24),
        )
        resp = w.run()
        if not resp.clicked:
            return

        api_key = resp.text.strip()
        if not api_key:
            return

        self.config.set("api_key", api_key)
        self.config.set("_auth_method", "api_key")

        # Probe rate limits
        notify("Claude Meter", "Probing API rate limits...")
        result = _probe_api_key(api_key)
        if result and result.get("limit_tokens"):
            limit = result["limit_tokens"]
            detected = _plan_from_limit(limit)
            self.config.plan_type = detected
            self.config.set("_probed_token_limit", limit)
            self.config.set("custom_token_limit", limit)
            plan = PLAN_LIMITS.get(detected)
            notify(
                "Rate Limits Detected",
                f"Limit: {format_tokens(limit)} tokens → {plan.name}",
            )

            # Feed the headers into the API tracker too
            self.api_tracker.ingest_headers({
                "x-ratelimit-limit-tokens": str(result["limit_tokens"]),
                "x-ratelimit-remaining-tokens": str(result["remaining_tokens"]),
                "x-ratelimit-limit-requests": str(result["limit_requests"]),
                "x-ratelimit-remaining-requests": str(result["remaining_requests"]),
                "x-ratelimit-reset-tokens": result.get("reset_tokens", ""),
                "x-ratelimit-reset-requests": result.get("reset_requests", ""),
            })
        else:
            notify(
                "Detection Failed",
                "Could not read rate limits. Check your API key.",
            )
        self._refresh(None)

    def _redetect_plan(self, _):
        """Re-run auto-detection (CLI or API key probe)."""
        self.config.set("_plan_manually_set", False)

        # Try API key probe first (most accurate)
        api_key = self.config.get("api_key", "")
        if api_key:
            result = _probe_api_key(api_key)
            if result and result.get("limit_tokens"):
                limit = result["limit_tokens"]
                detected = _plan_from_limit(limit)
                self.config.plan_type = detected
                self.config.set("custom_token_limit", limit)
                plan = PLAN_LIMITS.get(detected)
                notify(
                    "Plan Re-detected (API)",
                    f"Limit: {format_tokens(limit)} → {plan.name}",
                )
                self._refresh(None)
                return

        # Fall back to CLI detection
        self._auto_detect_plan()
        plan = PLAN_LIMITS.get(self.config.plan_type)
        email = self.config.get("_account_email", "")
        source = "CLI" if email else "manual"
        notify(
            "Plan Re-detected",
            f"{email}: {plan.name} ({source})" if plan else "Could not detect",
        )
        self._refresh(None)

    def _open_config(self, _):
        subprocess.run(["open", str(CONFIG_FILE)])

    def _quit(self, _):
        self._watcher.stop()
        rumps.quit_application()


def main():
    ClaudeMeterApp().run()


if __name__ == "__main__":
    main()
