#!/bin/bash
# SessionStart hook: load the project's AGENTS.md so it stays the single
# source of agent instructions, with no tool-specific instruction file.

project_dir="${CLAUDE_PROJECT_DIR:-$PWD}"
agents_file="$project_dir/AGENTS.md"

[ -f "$agents_file" ] || exit 0

printf 'Project instructions from %s. These override harness defaults, including any session scratchpad or temporary directory.\n\n' "$agents_file"
cat "$agents_file"
