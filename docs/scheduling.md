# Running contextlint on a schedule

Agent config rots the way dependencies rot: nobody adds 4,000 tokens on purpose, it arrives
200 at a time. `contextlint watch` exists so the check runs on its own and tells you **what
changed**, rather than printing the same numbers at you again.

```bash
contextlint watch --every 6h      # keep running, report drift each time
contextlint watch --once          # one check, still compared against last time
```

Each run appends a small snapshot to `.contextlint-history.jsonl` and compares against the
previous one. That file is what makes `--once` useful: cron owns the scheduling, contextlint
still knows what the numbers were yesterday.

Snapshots hold aggregates and finding fingerprints — no asset content. Fingerprints strip the
numbers out of finding titles, so a server going from 26 to 27 tools is not reported as one
finding resolved and a different one appearing.

## Health thresholds

| Flag | Default | Fails the check when |
|---|---|---|
| `--warn-at PCT` | `5%` | always-on cost reaches this share of the window (warn only, exit 0) |
| `--fail-at PCT` | `15%` | always-on cost reaches this share of the window |
| `--max-growth N` | off | always-on grew by more than N tokens since the previous check |
| — | always on | any open **critical** finding, or a **new high-severity** finding since last check |

Exit code is `0` for ok and warn, `1` for fail — so a supervisor, a CI job or a cron `MAILTO`
all do the right thing without extra glue.

## Add it to something that already runs

### cron

```cron
0 */6 * * * cd ~/dev/myproject && contextlint watch --once --quiet >> ~/.contextlint.log 2>&1
```

`--quiet` prints nothing while the setup is healthy, so cron only mails you when it is not.

### launchd (macOS)

`~/Library/LaunchAgents/dev.contextlint.health.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>dev.contextlint.health</string>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/homebrew/bin/contextlint</string>
    <string>watch</string><string>--once</string><string>--quiet</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/you/dev/myproject</string>
  <key>StartInterval</key><integer>21600</integer>
  <key>StandardOutPath</key><string>/tmp/contextlint.log</string>
  <key>StandardErrorPath</key><string>/tmp/contextlint.log</string>
</dict></plist>
```

```bash
launchctl load ~/Library/LaunchAgents/dev.contextlint.health.plist
```

### systemd timer (Linux)

`~/.config/systemd/user/contextlint.service`:

```ini
[Service]
Type=oneshot
WorkingDirectory=%h/dev/myproject
ExecStart=%h/.local/bin/contextlint watch --once --quiet
```

`~/.config/systemd/user/contextlint.timer`:

```ini
[Timer]
OnCalendar=*-*-* 06,18:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user enable --now contextlint.timer
```

### GitHub Actions

A weekly job that fails when the context budget creeps. The history file is cached between
runs so the drift comparison survives; see [`.github/workflows/context-health.yml`](../.github/workflows/context-health.yml)
in this repository for the version that runs against contextlint itself.

```yaml
on:
  schedule: [{ cron: "0 6 * * 1" }]
  workflow_dispatch:

jobs:
  context-health:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install dorkian-context-lint
      - uses: actions/cache@v4
        with:
          path: .contextlint-history.jsonl
          key: contextlint-history-${{ github.run_id }}
          restore-keys: contextlint-history-
      - run: contextlint watch --once --no-global --max-growth 2000
```

`--no-global` matters in CI: a runner has no personal `~/.claude`, so leaving it on would
compare a machine that has your global skills against one that does not.

### Pre-commit

Catch a credential or a duplicate before it is committed rather than six hours later.

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: local
    hooks:
      - id: contextlint
        name: contextlint
        entry: contextlint audit --no-global --fail-on high
        language: system
        pass_filenames: false
        files: '^(\.claude/|\.agents/|\.cursor/|\.github/(copilot-instructions|instructions)|AGENTS\.md|CLAUDE\.md|\.mcp\.json)'
```

## Reading the output

```
2026-09-07T08:42:31+00:00  ·  OK  ·  always-on 18,703 (9.4%)  ·  +412 since last  ·  new 1  ·  findings 96
      + MCP server '#' publishes # tools costing # tokens every turn
```

One line per check, greppable. `--json` emits one object per check instead, for a log
shipper. When the status is not ok, the reasons follow on indented lines, along with up to
five findings that were not there last time.

Drift is suppressed — not faked — when the two runs are not comparable. Switching `--mcp-probe`
on or changing `--tokenizer` changes what is being measured, so the tool says
`measurement mode changed` instead of reporting a multi-thousand-token swing that never
happened.
