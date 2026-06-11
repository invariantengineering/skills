# skills

A monorepo of [Claude Code](https://docs.claude.com/en/docs/claude-code) skills.
Each skill is packaged as its own self-contained plugin, so you can install
exactly the skills you want — nothing more.

The repo root hosts a single marketplace manifest
([`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json)) that
lists every plugin. Each plugin lives in its own subfolder with its own
`plugin.json` and `skills/` directory.

## Available skills

| Skill | Category | Description |
|-------|----------|-------------|
| [commit-and-push](commit-and-push/) | dev-tools | Safely commit a completed logical chunk of work and push it to the remote branch. |
| [pipe-down](pipe-down/) | productivity | Run exactly one shell command per Bash call so commands match Claude Code's permission allowlist and run without re-prompting. |

## Installing a skill

First add this marketplace (once):

```
/plugin marketplace add invariantengineering/skills
```

Then install any skill by name:

```
/plugin install pipe-down@skills
```

Repeat the `install` step for each skill you want.

## Adding a new skill

Every skill is a plugin. To add one:

1. **Copy the template.** Duplicate the [`_template/`](_template/) folder and
   rename it to your skill's name (kebab-case), e.g. `my-new-skill/`.
2. **Rename the inner skill folder.** Rename
   `my-new-skill/skills/_template/` to `my-new-skill/skills/my-new-skill/`.
3. **Fill in `plugin.json`.** Set `name` and `description`; keep `version` at
   `1.0.0` for a new skill.
4. **Fill in `SKILL.md`.** Replace every `TODO` in the frontmatter and body.
   The `name` must match the folder name; the `description` is how Claude
   discovers the skill.
5. **Register it.** Add an entry to the `plugins` array in
   [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) with
   `source: "./my-new-skill"` and a `category`.
6. **Add a row** to the table above.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full conventions and how to
test a skill locally.

## License

[MIT](LICENSE) © 2026 Invariant Engineering
