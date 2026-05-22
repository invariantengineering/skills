# Contributing

Conventions for adding and maintaining skills in this monorepo.

## One plugin per skill

Each skill is a standalone, independently installable plugin. A plugin folder
contains exactly one skill. Do not bundle multiple skills into a single plugin.

## Folder naming

- Use **kebab-case** for all plugin and skill folder names (`pipe-down`, not
  `PipeDown` or `pipe_down`).
- The plugin folder, the inner `skills/<name>/` folder, and the `name` fields
  in both `plugin.json` and `SKILL.md` must all match.

A plugin folder has this layout:

```
<skill-name>/
├── .claude-plugin/
│   └── plugin.json
└── skills/
    └── <skill-name>/
        └── SKILL.md
```

## `plugin.json` rules

Required fields:

- `name` — matches the folder name (kebab-case).
- `description` — one concise line.
- `version` — semver; start new skills at `1.0.0`.
- `author` — `{ "name": ..., "url": ... }` block.

## `SKILL.md` frontmatter rules

`SKILL.md` must begin with YAML frontmatter containing exactly two fields:

```yaml
---
name: <skill-name>
description: When the user wants to ... Also use when ...
---
```

- `name` — matches the folder name.
- `description` — written for **discovery**: lead with the trigger conditions
  and include key phrases that should activate the skill. This is the text
  Claude uses to decide when to invoke the skill, so be specific.

## Registering a new plugin

Add an entry to the `plugins` array in
`.claude-plugin/marketplace.json`:

```json
{
  "name": "my-new-skill",
  "source": "./my-new-skill",
  "description": "One-line description.",
  "version": "1.0.0",
  "category": "productivity"
}
```

- `source` must be `"./<plugin-folder>"` — a relative path to the plugin
  subfolder, **never** `"./"`.
- `category` groups the skill in the marketplace (e.g. `productivity`,
  `writing`, `dev-tools`).

Then add a row to the table in `README.md`.

## Starting from the template

Copy `_template/` and follow the steps in
[README.md → Adding a new skill](README.md#adding-a-new-skill). Replace every
`TODO` marker before opening a pull request.

## Testing a skill locally

You can install from a local checkout instead of GitHub:

```
/plugin marketplace add /absolute/path/to/skills
/plugin install <skill-name>@skills
```

Then start a fresh Claude Code session and confirm the skill is listed and
triggers on the phrases described in its `SKILL.md` `description`. After
editing a skill, remove and re-add the marketplace to pick up changes:

```
/plugin marketplace remove skills
/plugin marketplace add /absolute/path/to/skills
```
