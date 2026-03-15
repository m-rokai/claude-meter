"""Configuration management for Claude Meter."""

import json
from pathlib import Path
from .constants import PlanType, DEFAULT_THRESHOLDS, DEFAULT_REFRESH_INTERVAL

CONFIG_DIR = Path.home() / ".claude-meter"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "plan_type": PlanType.PRO.value,
    "api_key": "",
    "notification_thresholds": DEFAULT_THRESHOLDS,
    "refresh_interval": DEFAULT_REFRESH_INTERVAL,
    "usage_multiplier": 1.0,  # Set >1 during Anthropic double/triple usage events
    "show_percentage": True,
    "claude_dir": str(Path.home() / ".claude"),
    "rate_limit_window_start": None,
    "last_rate_limit_hit": None,
    "custom_token_limit": None,  # Override estimated plan limit
    "launch_at_login": False,
    "notification_sound": True,
}


class Config:
    def __init__(self):
        self._config = {}
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
                    saved = json.load(f)
                self._config = {**DEFAULT_CONFIG, **saved}
            except (json.JSONDecodeError, OSError):
                self._config = DEFAULT_CONFIG.copy()
                self.save()
        else:
            self._config = DEFAULT_CONFIG.copy()
            self.save()

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self._config, f, indent=2)

    def get(self, key, default=None):
        return self._config.get(key, default)

    def set(self, key, value):
        self._config[key] = value
        self.save()

    @property
    def plan_type(self) -> PlanType:
        try:
            return PlanType(self._config.get("plan_type", "pro"))
        except ValueError:
            return PlanType.PRO

    @plan_type.setter
    def plan_type(self, value: PlanType):
        self._config["plan_type"] = value.value
        self.save()

    @property
    def usage_multiplier(self) -> float:
        return float(self._config.get("usage_multiplier", 1.0))

    @usage_multiplier.setter
    def usage_multiplier(self, value: float):
        self._config["usage_multiplier"] = value
        self.save()

    @property
    def refresh_interval(self) -> int:
        return int(self._config.get("refresh_interval", DEFAULT_REFRESH_INTERVAL))

    @property
    def claude_dir(self) -> Path:
        return Path(self._config.get("claude_dir", str(Path.home() / ".claude")))

    @property
    def token_limit(self) -> int:
        """Effective token limit, accounting for custom override and multiplier."""
        from .constants import PLAN_LIMITS
        custom = self._config.get("custom_token_limit")
        if custom:
            return int(custom * self.usage_multiplier)
        plan = PLAN_LIMITS.get(self.plan_type)
        if plan:
            return int(plan.output_tokens_per_window * self.usage_multiplier)
        return 300_000
