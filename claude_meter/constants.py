"""Plan limits, thresholds, and display constants."""

from enum import Enum
from dataclasses import dataclass


class PlanType(Enum):
    FREE = "free"
    PRO = "pro"
    MAX_5X = "max_5x"
    MAX_20X = "max_20x"
    TEAM = "team"
    ENTERPRISE = "enterprise"
    API = "api"


@dataclass
class PlanLimits:
    name: str
    output_tokens_per_window: int
    window_hours: float
    description: str


# Estimated output token limits per rate window.
# These are approximate and may change. Users can override via custom_token_limit.
# Source: Anthropic docs + community observations.
PLAN_LIMITS = {
    PlanType.FREE: PlanLimits(
        name="Free",
        output_tokens_per_window=8_000,
        window_hours=5,
        description="Free tier — very limited",
    ),
    PlanType.PRO: PlanLimits(
        name="Pro ($20/mo)",
        output_tokens_per_window=300_000,
        window_hours=5,
        description="Standard Pro plan",
    ),
    PlanType.MAX_5X: PlanLimits(
        name="Max 5x ($100/mo)",
        output_tokens_per_window=1_500_000,
        window_hours=5,
        description="Max plan with 5x Pro usage",
    ),
    PlanType.MAX_20X: PlanLimits(
        name="Max 20x ($200/mo)",
        output_tokens_per_window=6_000_000,
        window_hours=5,
        description="Max plan with 20x Pro usage",
    ),
    PlanType.TEAM: PlanLimits(
        name="Team ($30/user/mo)",
        output_tokens_per_window=300_000,
        window_hours=5,
        description="Team plan — Pro-level per user",
    ),
    PlanType.ENTERPRISE: PlanLimits(
        name="Enterprise",
        output_tokens_per_window=600_000,
        window_hours=5,
        description="Enterprise plan — custom limits",
    ),
    PlanType.API: PlanLimits(
        name="API (Pay-as-you-go)",
        output_tokens_per_window=0,  # User configures
        window_hours=1,
        description="API key — rate limits vary by tier",
    ),
}

# Notification thresholds (percentage of limit used)
DEFAULT_THRESHOLDS = [60, 80, 90, 95]

# Usage level boundaries
USAGE_LEVELS = {
    "low": (0, 60),
    "medium": (60, 80),
    "high": (80, 95),
    "critical": (95, 101),
}

# Menu bar status indicators
STATUS_ICONS = {
    "low": "🟢",
    "medium": "🟡",
    "high": "🟠",
    "critical": "🔴",
    "unknown": "⚪",
    "rate_limited": "⛔",
}

# How often to auto-refresh (seconds)
DEFAULT_REFRESH_INTERVAL = 30
