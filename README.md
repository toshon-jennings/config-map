# config-map

A beautiful terminal map of your configuration files.

<p align="center">
  <img src="https://raw.githubusercontent.com/toshon-jennings/config-map/main/assets/demo.png" alt="config-map demo" width="700">
</p>

Scans `~/.config/` recursively and your top-level dotfiles, then displays each
file with path, size, last-modified, format, line count, and a **type-specific
summary** — extracted keys for JSON/YAML/TOML, alias/export counts for shell
configs, variable counts for `.env`, and more.

Runs in ~3 seconds. No configuration needed. Read-only.

---

## Quick start

```bash
pip install config-map
config-map
```

That's it. You get a rich terminal dashboard showing every config file on your
machine, grouped by directory, with format, size, line count, and a short
summary of what each file does.

---

## What you see

Each file is displayed in a table row with:

| Column | What it shows |
|--------|---------------|
| **File** | Path (relative to ~) |
| **Format** | JSON / YAML / TOML / ENV / SHELL / PLIST / INI, etc. |
| **Size** | Human-readable (B / KB / MB) |
| **Lines** | Line count (skips files >5 MB) |
| **Modified** | Last modified date and time |
| **Purpose / Summary** | What the file is for + extracted structure |

### Type-specific summaries

The script recognizes 60+ config file types and extracts meaningful summaries:

- **JSON** → top-level keys (e.g., `name, version, main, scripts, dependencies`)
- **YAML** → top-level keys
- **TOML** → top-level sections/keys (e.g., `[tool.poetry], [build-system]`)
- **.env** → variable count (e.g., `12 variables`)
- **Shell configs** → alias/export/function counts (e.g., `9 aliases, 21 exports`)
- **.gitconfig** → section list (e.g., `user, core, alias, push, pull`)
- **SSH config** → Host entries
- **Plists** → top-level keys
- **INI/CFG** → section headers

A header panel shows aggregate stats: total file count, total size, format
breakdown, and number of directories scanned.

---

## Usage

```bash
config-map [OPTIONS]

Options:
  --demo            Render with synthetic data (for screenshots, no filesystem access)
  --full            Scan everything (default)
  --config          Only scan ~/.config/
  --dotfiles        Only scan top-level dotfiles (~/.zshrc, ~/.gitconfig, etc.)
  --search TEXT     Filter by path/name substring (case-insensitive)
  --min-size SIZE   Only show files >= this size (e.g., 1k, 100k, 1m)
  --no-color        Disable colored output
  --version         Show version
  --help            Show help message
```

### Examples

```bash
# Find all Hermes-related config files
config-map --search herme

# See only substantial config files (>= 10KB)
config-map --min-size 10k

# Focus on just your shell and git configs
config-map --dotfiles --search zsh
config-map --dotfiles --search git

# Audit just ~/.config/
config-map --config
```

---

## How it works

1. **Discovery** — Walks `~/.config/` recursively and all top-level dotfiles in
   `~/`. Skips known noise dirs (`.cache`, `node_modules`, GPU caches, etc.) and
   binary file extensions.
2. **Analysis** — For each file, detects format and runs the appropriate
   extractor. Large files (>5 MB) are stat'd but never read — keeps it fast.
3. **Display** — Groups files by parent directory, sorts by size descending,
   and renders color-coded tables via the `rich` library.

Config directories that are mostly caches (`.hermes`, `.vscode`, `.lmstudio`,
`.gemini`, `.claude`, `.cursor`, etc.) are scanned **shallowly** — only
top-level files, no recursion. This avoids walking gigabytes of models and
caches.

---

## Performance

On a typical macOS system with ~30 config directories:

- **Scan time**: ~3 seconds
- **Memory**: Minimal (files are processed one at a time)
- **Disk**: Read-only. Never writes anything.

## Requirements

- Python 3.7+
- [rich](https://github.com/Textualize/rich) >= 10.0 (installed automatically)

Works on macOS and Linux.

---

## Use cases

- **Audit your dotfiles**: See what's accumulated across years of tool installs
- **Find stale configs**: Sort by modified date to spot configs from uninstalled tools
- **Discover forgotten settings**: That `.env` from a project you abandoned two years ago
- **Document your system**: Screenshot the output for a system readme
- **Clean up**: Identify which config directories are eating disk space

---

## Project links

| | |
|---|---|
| **Source** | [github.com/toshon-jennings/config-map](https://github.com/toshon-jennings/config-map) |
| **PyPI** | [pypi.org/project/config-map](https://pypi.org/project/config-map) |
| **Issues** | [GitHub Issues](https://github.com/toshon-jennings/config-map/issues) |
| **Changelog** | [CHANGELOG.md](CHANGELOG.md) |
| **Contributing** | [CONTRIBUTING.md](CONTRIBUTING.md) |

---

## Comparison

| Tool | What it does | How config-map differs |
|------|-------------|----------------------|
| `ls -la ~/.*` | Lists files | config-map adds format detection, summaries, size, line counts |
| `find ~/.* -type f` | Finds files | config-map groups, classifies, and extracts structure |
| `du -sh ~/.*` | Shows disk usage | config-map shows *content*, not just size |
| `mackup` | Backs up configs | config-map audits; doesn't modify anything |

---

## FAQ

**Does config-map modify any files?**

No. It's read-only. It never writes, deletes, or moves anything.

**Will it pick up secrets from my .env files?**

It counts variables in `.env` files but never displays their *values*. Sensitive
content stays on disk.

**Why does it skip some directories recursively?**

Directories known to contain large caches or downloaded models (`.hermes`,
`.vscode`, `.lmstudio`, etc.) are scanned at the top level only. This keeps
scan time in seconds rather than minutes. Add your own large dotdirs to
`SHALLOW_DOTDIRS` in the source if needed.

**Can I run it on a remote server?**

Yes. It reads `~` (the current user's home) so it works anywhere you have a
home directory and Python 3.7+. It's particularly useful for auditing Linux
server configs.

---

## License

MIT © 2026 Toshon Jennings
