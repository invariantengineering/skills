# Claude Code setup

`AGENTS.md` is the single source of agent instructions in every repository.
Claude Code does not need a separate `CLAUDE.md`. Two user-level hooks give it
the same behavior as other agents:

| Hook | Event | What it does |
|------|-------|--------------|
| [`load-agents-md.sh`](hooks/load-agents-md.sh) | `SessionStart` | Loads the project's `AGENTS.md` into context and marks it as overriding harness defaults. |
| [`block-system-tmp.sh`](hooks/block-system-tmp.sh) | `PreToolUse` | Denies shell commands and file writes that target `/tmp`, `/private/tmp`, `$TMPDIR`, or `/var/folders`, and tells the agent to use `.scratch/` instead. |

Claude Code gives each session a scratchpad under the system temp directory
and tells the agent to use it. That built-in instruction can't be turned off,
so the `PreToolUse` hook enforces the repository-local `.scratch/` rule.

## Install on a new machine

Requires `jq`.

1. Copy the hook scripts into your user Claude Code directory:

   ```bash
   mkdir -p ~/.claude/hooks
   ```

   ```bash
   cp claude-code/hooks/*.sh ~/.claude/hooks/
   ```

   ```bash
   chmod +x ~/.claude/hooks/load-agents-md.sh ~/.claude/hooks/block-system-tmp.sh
   ```

2. Merge the `hooks` block from [`settings.hooks.json`](settings.hooks.json)
   into `~/.claude/settings.json`. If that file already has a `hooks` key, add
   these entries to its existing arrays rather than replacing them.

3. Validate the settings file:

   ```bash
   jq -e '.hooks.PreToolUse[].hooks[].command' ~/.claude/settings.json
   ```

   Expected result: the command paths are printed and the exit status is 0.

4. Start a new Claude Code session. Settings are read at startup.

## Verify

In a new session inside any repository with an `AGENTS.md`:

- Ask for a file to be written to `/tmp/check.txt`. The write is blocked
  with a message pointing to `.scratch/`.
- Ask for a file to be written to `.scratch/check.txt`. The write succeeds.
- In the CLI, run `/hooks` to see both hooks listed.

## Updating

After changing a script in `claude-code/hooks/`, copy it to
`~/.claude/hooks/` again. Changes take effect in the next session.
