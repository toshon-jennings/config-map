# Changelog

All notable changes to config-map will be documented in this file.

## [1.0.0] — 2026-06-28

### Added
- Initial release
- Scans `~/.config/` recursively and top-level dotfiles
- Detects 15+ config formats: JSON, YAML, TOML, ENV, SHELL, PLIST, INI, CONF, GITCONFIG, etc.
- Type-specific summaries: extracted keys, alias/export counts, variable counts, git sections, SSH hosts, plists
- Groups output by parent directory, sorted by size descending
- Color-coded tables via `rich` library
- Aggregate stats panel (total files, size, format breakdown)
- `--search` filter for path/name substring matching
- `--min-size` filter to focus on substantial files
- `--config` / `--dotfiles` scope flags
- `--no-color` for piping/plain output
- `--version` flag
- Shallow scanning for known cache-heavy dotdirs (keeps scan ~3s)
- 5 MB file read cap (large files show size/format only, never read)
- Cross-platform: macOS and Linux, Python 3.7+
