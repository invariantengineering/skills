---
name: commit-and-push
description: >
  When the user wants to commit and push completed work, create a clean git
  commit for a coherent logical chunk and push it to the remote. Also use after
  implementing, fixing, refactoring, documenting, or otherwise finishing work
  that should be saved upstream. Do not use for WIP unless explicitly requested.
---

# commit-and-push

Turn completed work into a reviewed commit and push it to the appropriate
remote branch.

## Principles

- Inspect before staging. Never stage unknown changes blindly.
- Commit one coherent logical chunk at a time.
- Stage only files that belong to the intended chunk.
- Prefer existing project checks over invented commands.
- Do not push failing work unless the user explicitly asks for it.
- Do not amend, rebase, force-push, reset, delete branches, or otherwise
  rewrite history unless explicitly requested.

## Safety stops

Stop and ask the user before staging or committing if any of these appear in
the changed files or diff:

- Secrets or local config: `.env`, `.env.*`, credentials, API keys, tokens,
  private keys, `*.pem`, `*.key`, `id_rsa`, `id_ed25519`.
- Database dumps, production data exports, or large unexplained binary files.
- Local editor files, logs, caches, build output, dependency folders, or other
  generated artifacts unless project conventions clearly require them.
- Changes on protected long-lived branches such as `main`, `master`,
  `production`, `prod`, `stage`, or `staging`, unless the user explicitly asked
  to commit there or the repository clearly uses direct commits to that branch.
- Unrelated changes that cannot be separated confidently from the intended
  logical chunk.

## Workflow

1. Confirm repository state:
   - `git rev-parse --show-toplevel`
   - `git status --short`
   - `git branch --show-current`
   - `git remote -v`
   - `git status -sb`

2. If there are no local file changes:
   - If `git status -sb` shows the branch is ahead of its upstream, push the
     existing commits.
   - If there is nothing to commit or push, report that the repository is
     clean.

3. Review all changes before staging:
   - `git diff --stat`
   - `git diff --name-status`
   - `git diff`
   - If anything is already staged, also inspect:
     - `git diff --cached --stat`
     - `git diff --cached --name-status`
     - `git diff --cached`

4. Summarize the intended commit in plain language:
   - What changed.
   - Which files belong in the commit.
   - Which files, if any, will remain uncommitted.
   - Any risk or check decision worth noting.

5. Run relevant checks when reasonably discoverable:
   - Prefer project scripts and documented commands.
   - Use the fastest relevant checks first.
   - Common commands include `npm test`, `npm run lint`,
     `npm run typecheck`, `npm run build`, `pnpm test`, `pnpm lint`,
     `pnpm typecheck`, `pnpm build`, `yarn test`, `yarn lint`,
     `yarn typecheck`, `yarn build`, `pytest`, `ruff check .`, `mypy .`,
     `go test ./...`, and `cargo test`.
   - Do not spend excessive time searching. If no obvious check exists, say so
     and continue.

6. Stage the intended files:
   - Prefer `git add <specific-files>`.
   - Use `git add -A` only after reviewing all changed files and confirming
     they all belong to the same commit.
   - Verify staged content with:
     - `git status --short`
     - `git diff --cached --stat`
     - `git diff --cached --name-status`

7. Write a concise commit message:
   - Prefer conventional style when it fits: `feat:`, `fix:`, `refactor:`,
     `docs:`, `test:`, or `chore:`.
   - Keep the subject under about 72 characters when practical.
   - Add a short body only when it helps future readers understand why the
     change was made.

8. Commit:
   - `git commit -m "<subject>"`
   - For a useful body, use `git commit -m "<subject>" -m "<body>"`.

9. Push:
   - Run `git status -sb` to check upstream tracking.
   - If the branch tracks a remote branch, run `git push`.
   - If no upstream is configured, first run `git branch --show-current`, then
     push with `git push -u origin <branch-name>`.

10. Report the result:
    - Branch name.
    - Commit hash.
    - Commit message.
    - Push destination.
    - Checks run and whether they passed.
    - Files intentionally left uncommitted.
