# cswap-wrappers

Automatic switching between two company Claude accounts with
[claude-swap](https://github.com/realiti4/claude-swap) (`cswap`), plus a Claude Code hook that
wakes a session after a rate-limit failure so it can resume its subagents.

## What it does

`bin/cswap-priority` reads `cswap list --json` and decides which account should be active:

- Best phase first: accounts with Fable headroom, else accounts with 5h/7d headroom (Opus and
  everything else), else stay put.
- It stays on the active account while that account qualifies. When it stops qualifying, it takes the
  first qualifying account by number (`--order "2 1"` or `CSWAP_PRIORITY_ORDER` to change).
- An account qualifies below 90% on the 5-hour window (`--threshold-5h`) and below 95% on the 7-day
  and Fable windows (`--threshold`).

Modes:

- no flag: one tick, exit code 0 switched, 1 error, 2 nothing to do (`--dry-run` only reports).
- `--loop 20`: a long-lived watcher, one tick every 20 seconds.
- `--revive`: a Claude Code `StopFailure` hook. On a rate-limit failure it looks for a usable
  account (swapping at once if needed), waits 35 seconds, then exits 2 so `asyncRewake` wakes the
  session with an instruction to resume failed subagents. The wait is there because Claude Code
  caches the macOS keychain login for 30 seconds per process, so a session cannot use the new
  account sooner. It does not wake when both accounts are spent, when no recent swap explains the
  failure, or within 5 minutes of the last wake of the same session.

## Install (macOS)

```sh
mkdir -p ~/bin && cp bin/cswap-priority ~/bin/ && chmod +x ~/bin/cswap-priority
cp launchd/com.bloureiro.cswap-priority.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.bloureiro.cswap-priority.plist
launchctl kickstart gui/$(id -u)/com.bloureiro.cswap-priority
```

The `kickstart` is required. On the Mac this was built on (Darwin 25.6.0), launchd logs "pending
spawn, domain in on-demand-only mode" and never starts RunAtLoad, StartInterval or KeepAlive jobs
for newly bootstrapped agents; only an on-demand start works. So the agent runs its own loop and is
started by hand. After a reboot or re-login, check
`launchctl print gui/$(id -u)/com.bloureiro.cswap-priority` and kickstart again if it is not running.

The plist and the hook below use absolute `/Users/bloureiro` paths.

Add the hook to `~/.claude/settings.json`, next to any other `StopFailure` entries:

```json
"StopFailure": [
  {
    "hooks": [
      {
        "type": "command",
        "command": "/Users/bloureiro/bin/cswap-priority --revive",
        "timeout": 300,
        "asyncRewake": true
      }
    ]
  }
]
```

## Stop

```sh
launchctl bootout gui/$(id -u)/com.bloureiro.cswap-priority
```

and remove the hook entry.

## Runtime files

- `~/Library/Logs/cswap-priority.log`: switches, errors and every hook decision.
- `~/.cache/cswap-priority.tick`: heartbeat of the last tick.
- `~/.cache/cswap-priority.swap`, `.last`, `.woke.<session>`: last swap, last logged state, last wake.

## Limits

- cswap serves usage readings up to 180 seconds old (`poll_policy.SERVE_TTL_S`), and polling faster
  risks the usage endpoint's rate limit. A burst can pass the line before a swap; the hook is the
  safety net.
- A message sent on a spent account before the swap is picked up still fails once.
- `asyncRewake` is an undocumented hook option (marked internal in Claude Code 2.1.294).
- A manual `cswap switch` onto an account that does not qualify is reverted within 20 seconds.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Standard library only; a fake `cswap` and a temporary `HOME` keep real accounts and state untouched.
The revive tests take about 30 seconds.
