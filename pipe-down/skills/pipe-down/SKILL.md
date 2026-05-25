---
name: pipe-down
description: >
  Run exactly one shell command per Bash call. No chaining, no pipes, no
  command substitution, no subshells. Keeping every command simple and
  canonical lets it match Claude Code's permission allowlist, so approved
  commands run without re-prompting. Use whenever running terminal, shell,
  or Bash commands.
---

# pipe-down

Run **one command per Bash call**. Never combine commands into a single
invocation. Each call should be the simplest, most canonical form of one
operation.

## Why this matters

Claude Code checks every Bash command against the permission allowlist
(`permissions.allow` in settings, e.g. `Bash(git status:*)`,
`Bash(npm run test:*)`). Rules match by **command prefix**.

A compound command — `git status && npm test | grep fail` — is one opaque
string. It does not match any single prefix rule, so Claude Code prompts for
approval *every time*. Worse, each unique combination is novel, so "always
allow" approvals never accumulate.

Run those as three separate calls — `git status`, then `npm test`, then read
the output yourself — and each one matches its own allow rule and runs with
no interruption. Simple commands stay on the whitelist. Clever one-liners
fall off it.

## The one rule

> One command. One Bash call. Nothing combining it with another.

## Banned by default

Do not use these to glue commands together:

| Operator | Name |
|----------|------|
| `&&` `\|\|` | conditional chaining |
| `;` | sequential chaining |
| `\|` | pipes |
| `&` | backgrounding |
| `$(...)` `` `...` `` | command substitution |
| `<(...)` `>(...)` | process substitution |
| `(...)` `{ ...; }` | subshells / group commands |
| `<<EOF` | heredocs used to build one-liners |

Plain redirections (`>`, `>>`, `2>&1`), flags, and globs are fine — they are
part of a single command, not a way to chain two.

## Do this instead

- **Need B only if A succeeds?** Run A. Read the result. Then decide on B.
  You are the `&&`.
- **Need to filter output?** Don't pipe to `grep`/`head`/`awk`. Run the
  command plain and read its output yourself, or use the tool's own flags —
  `git log -n 5` not `git log | head -5`, `grep -r foo src` not
  `cat ... | grep foo`.
- **Need to change directory?** Run `cd path` as its own call. The Bash
  session persists, so every later call runs there.
- **Need an environment variable?** Run `export VAR=value` as its own call.
  It persists for the rest of the session.
- **Writing or editing a file?** Use the Write/Edit tools. Never
  `cat <<EOF > file` or `echo ... >> file` for content.

## Examples

Avoid → Prefer:

- `cd backend && npm install`
  → `cd backend` · then · `npm install`
- `npm run build && npm run test`
  → `npm run build` · then · `npm run test`
- `cat package.json | grep version`
  → `grep version package.json`
- `ls -la $(git rev-parse --show-toplevel)`
  → `git rev-parse --show-toplevel` · then · `ls -la <that path>`
- `mkdir dist && cp -r src/* dist/`
  → `mkdir dist` · then · `cp -r src/ dist/`
- `git add . && git commit -m "fix"`
  → `git add .` · then · `git commit -m "fix"`

## Genuine exceptions

Keep these rare and deliberate:

- A single command that *is* one command even though it looks compound —
  `find . -name '*.log' -delete`, `git log --oneline -n 20`. These are fine;
  they're one invocation.
- A pipe with no flag-based alternative and no separable steps. Prefer the
  dedicated tool first (`pgrep node` over `ps aux | grep node`). If a pipe is
  truly unavoidable, use it — just know that command won't be allowlisted.
- The user explicitly asks for a combined one-liner.

## Persistence

This applies to **every Bash call for the whole session**. No drift back to
chained commands after many turns. Off only if the user says so.
