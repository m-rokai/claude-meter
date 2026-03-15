# Claude Meter

A macOS menu bar app that tracks your Claude AI usage, rate limits, and reset times in real time.

![macOS](https://img.shields.io/badge/macOS-000000?style=flat&logo=apple&logoColor=white)
![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)

<!--
TODO: Add screenshot here after first launch
![screenshot](assets/screenshot.png)
-->

## Features

- **Live usage percentage** in your menu bar — see how much of your rate-limit window you've used
- **Auto-detects your plan** via `claude auth status` (Pro, Max 5x, Max 20x, Team, Enterprise)
- **Real token counting** — reads actual per-message token usage from Claude Code session files
- **Rolling window tracking** — estimates usage within your 5-hour rate-limit window
- **Reset countdown** — know exactly when your oldest tokens fall off the window
- **Rate limit button** — mark when you're rate limited, get notified when it resets
- **Usage multiplier** — track Anthropic's double/triple usage events
- **API key detection** — paste your API key to probe exact `x-ratelimit-limit-tokens` from response headers
- **7-day usage history** — daily breakdown with bar charts
- **macOS notifications** — alerts at 60%, 80%, 90%, 95% usage
- **File watcher** — auto-refreshes instantly when Claude Code writes new data
- **Runs as a native .app** — no Dock icon, just a clean menu bar item

## Install

### Option A: Download the app (easiest)

Download `Claude Meter.app` from [Releases](../../releases), move it to `/Applications`, and double-click.

### Option B: Build from source

```bash
git clone https://github.com/m-rokai/claude-meter.git
cd claude-meter
pip3 install -r requirements.txt

# Run directly
python3 -m claude_meter

# Or build a .app bundle
make build                  # builds to dist/Claude Meter.app
make app                    # builds + copies to /Applications
```

### Option C: pip install

```bash
pip3 install -e .
claude-meter
```

## How it works

### Plan detection

On startup, Claude Meter automatically detects your plan:

1. **`claude auth status`** — runs the Claude Code CLI (non-invasive, no keychain access) to read your `subscriptionType`
2. **API key probe** — if you enter an API key via Settings, makes a single minimal API call and reads the `x-ratelimit-limit-tokens` response header for your exact limit
3. **Manual** — pick your plan from the Settings menu

Detection re-runs every 5 minutes to catch account changes.

### Token tracking

Claude Code writes per-message token usage to session files at `~/.claude/projects/<project>/<session>.jsonl`. Each assistant response includes an exact `output_tokens` count from the API. Claude Meter sums these within your rolling rate-limit window (typically 5 hours) to calculate real usage.

This is **not** an estimate — it's the actual token count from every API response.

### What you see

| Menu bar | Meaning |
|----------|---------|
| 🟢 12% | Low usage — plenty of capacity |
| 🟡 67% | Medium — be mindful |
| 🟠 88% | High — approaching limit |
| 🔴 97% | Critical — rate limit imminent |
| ⛔ | Rate limited — countdown to reset |

Click the icon for the full dropdown:

```
Usage: 12.3%
Tokens: 245.2K / 6.0M
Messages today: 847
Active sessions: 2
─────────────────────
Window resets in ~3h 42m
Window: 5h | 312 msgs in window
─────────────────────
Account: you@example.com
Plan: Max 20x ($200/mo)
Multiplier: 1.0x
─────────────────────
Total sessions: 42
Total messages: 12,847
Total tokens: 8.2M
Models: opus-4-6, opus-4-5-20251101
─────────────────────
Last 7 Days
  2026-03-14  ████░░░░░░  245.2K
  2026-03-13  ██████░░░░  380.1K
  ...
─────────────────────
I Got Rate Limited
Clear Rate Limit
─────────────────────
Refresh Now
Settings ▸
Quit Claude Meter
```

## Configuration

Settings are stored in `~/.claude-meter/config.json`. Edit directly or use the Settings menu.

| Setting | Default | Description |
|---------|---------|-------------|
| `plan_type` | auto-detected | `free`, `pro`, `max_5x`, `max_20x`, `team`, `enterprise`, `api` |
| `usage_multiplier` | `1.0` | Set `2.0` for double-usage events, `3.0` for triple, etc. |
| `custom_token_limit` | `null` | Override the plan's estimated limit with an exact number |
| `notification_thresholds` | `[60, 80, 90, 95]` | Usage percentages that trigger notifications |
| `refresh_interval` | `30` | Auto-refresh interval in seconds |
| `api_key` | `""` | Anthropic API key for direct rate-limit probing |

## Auto-start at login

**System Settings > General > Login Items > + > Claude Meter**

## Project structure

```
claude-meter/
├── claude_meter/
│   ├── app.py              # Main menu bar app (rumps)
│   ├── config.py           # ~/.claude-meter/config.json management
│   ├── constants.py        # Plan limits, thresholds, display icons
│   ├── notifications.py    # macOS notifications via osascript
│   ├── utils.py            # Token formatting, time helpers
│   ├── watcher.py          # File system watcher (watchdog)
│   └── trackers/
│       ├── claude_code.py  # Reads ~/.claude/ session data + plan detection
│       └── api_tracker.py  # API rate-limit header tracking
├── assets/
│   └── icon.icns           # App icon
├── entry.py                # PyInstaller entry point
├── Claude Meter.spec       # PyInstaller build spec
├── Makefile                # install, run, build, app, clean
├── pyproject.toml
├── requirements.txt
└── LICENSE
```

## Contributing

PRs welcome! Some ideas for future work:

- [ ] Auto-detect rate limiting from Claude Code error output
- [ ] Homebrew cask formula
- [ ] DMG installer with drag-to-Applications
- [ ] API proxy mode for automatic header capture
- [ ] Multiple account / org support
- [ ] Usage graphs in a native popover window
- [ ] SwiftUI rewrite for smaller binary size
- [ ] Linux / Windows support (different menu bar frameworks)

```bash
# Dev setup
git clone https://github.com/m-rokai/claude-meter.git
cd claude-meter
pip3 install -e .
python3 -m claude_meter
```

## License

MIT — see [LICENSE](LICENSE).
