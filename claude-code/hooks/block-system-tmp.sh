#!/bin/bash
# PreToolUse hook: deny shell commands and file writes that target system
# temporary directories. Temporary work belongs in the repository's ignored
# .scratch/ directory.

input=$(cat)
tool=$(jq -r '.tool_name // ""' <<<"$input")

case "$tool" in
  Bash) target=$(jq -r '.tool_input.command // ""' <<<"$input") ;;
  Write|Edit) target=$(jq -r '.tool_input.file_path // ""' <<<"$input") ;;
  NotebookEdit) target=$(jq -r '.tool_input.notebook_path // ""' <<<"$input") ;;
  *) exit 0 ;;
esac

# Absolute /tmp or /private/tmp, macOS per-user temp (/var/folders), or $TMPDIR.
# Relative paths such as .scratch/tmp are allowed.
pattern='(^|[^[:alnum:]_.-])(/private)?/tmp(/|$|[^[:alnum:]_.-])|/var/folders/|\$\{?TMPDIR'

if grep -Eq "$pattern" <<<"$target"; then
  reason='Blocked: temporary files must stay inside the repository. Use .scratch/ at the repository root (create it if missing and keep it git-ignored) instead of /tmp, /private/tmp, $TMPDIR, /var/folders, or the session scratchpad directory.'
  jq -n --arg reason "$reason" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: $reason
    }
  }'
fi

exit 0
