#!/usr/bin/env python3
"""
config-map — A beautiful terminal map of your configuration files.

Scans ~/.config/ recursively and your top-level dotfiles, then displays
each file with path, size, last-modified, format, line count, and a
type-specific summary (extracted keys for structured formats, counts for
.env / shell configs, etc.).

Requirements: Python 3.9+, Rich, and Textual

Usage:
    config-map                  # full report
    config-map --dotfiles       # only top-level dotfiles
    config-map --config         # only ~/.config
    config-map --search herme   # filter by path/name substring
    config-map --min-size 10k   # only files >= this size
"""

import argparse
import json
import os
import plistlib
import re
import sys
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.tree import Tree
    from rich import box
    from rich.columns import Columns
    from rich.rule import Rule
except ImportError:
    sys.stderr.write(
        "\n[ERROR] The 'rich' library is required but not installed.\n"
        "Install it with:  pip install rich\n\n"
    )
    sys.exit(1)


__version__ = "1.1.0"

HOME = Path.home()


# ---------------------------------------------------------------------------
# Known-config registry: maps filename/dir patterns to a label + extractor
# ---------------------------------------------------------------------------

def _first_yaml_keys(path: Path, max_keys: int = 6) -> Optional[str]:
    """Extract top-level YAML keys (simple line scanner, no PyYAML needed)."""
    try:
        keys = []
        for line in path.read_text(errors="replace").splitlines():
            stripped = line.rstrip()
            if not stripped or stripped.lstrip().startswith("#"):
                continue
            # top-level key: starts at column 0, ends with ':'
            if re.match(r"^[a-zA-Z0-9_\-]+\s*:", stripped):
                keys.append(stripped.split(":", 1)[0].strip())
            if len(keys) >= max_keys:
                break
        if keys:
            shown = ", ".join(keys[:max_keys])
            return shown + ("…" if len(keys) >= max_keys else "")
    except Exception:
        pass
    return None


def _first_toml_keys(path: Path, max_keys: int = 6) -> Optional[str]:
    """Extract top-level TOML keys/sections."""
    try:
        keys = []
        for line in path.read_text(errors="replace").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = re.match(r"^\[([^\]]+)\]", stripped)
            if m:
                keys.append("[" + m.group(1) + "]")
                continue
            m = re.match(r"^([a-zA-Z0-9_\-]+)\s*=", stripped)
            if m:
                keys.append(m.group(1))
            if len(keys) >= max_keys:
                break
        if keys:
            shown = ", ".join(keys[:max_keys])
            return shown + ("…" if len(keys) >= max_keys else "")
    except Exception:
        pass
    return None


def _first_json_keys(path: Path, max_keys: int = 6) -> Optional[str]:
    """Parse JSON and return top-level keys."""
    try:
        data = json.loads(path.read_text(errors="replace"))
        if isinstance(data, dict):
            keys = list(data.keys())
            shown = ", ".join(str(k) for k in keys[:max_keys])
            return shown + ("…" if len(keys) > max_keys else "")
    except Exception:
        pass
    return None


def _env_summary(path: Path) -> Optional[str]:
    """Count variables in a .env-style file."""
    try:
        lines = path.read_text(errors="replace").splitlines()
        vars = [
            l for l in lines
            if l.strip() and not l.strip().startswith("#") and "=" in l
        ]
        if vars:
            return f"{len(vars)} variable{'s' if len(vars) != 1 else ''}"
    except Exception:
        pass
    return None


def _shell_summary(path: Path) -> Optional[str]:
    """Count aliases, exports, and functions in a shell config."""
    try:
        text = path.read_text(errors="replace")
        aliases = len(re.findall(r"^\s*alias\s+", text, re.MULTILINE))
        exports = len(re.findall(r"^\s*export\s+", text, re.MULTILINE))
        funcs = len(re.findall(r"^\s*(function\s+\w+|\w+\s*\(\))", text, re.MULTILINE))
        parts = []
        if aliases:
            parts.append(f"{aliases} alias{'es' if aliases != 1 else ''}")
        if exports:
            parts.append(f"{exports} export{'s' if exports != 1 else ''}")
        if funcs:
            parts.append(f"{funcs} func{'s' if funcs != 1 else ''}")
        return ", ".join(parts) if parts else None
    except Exception:
        pass
    return None


def _ssh_config_summary(path: Path) -> Optional[str]:
    """Count Host entries in an SSH config."""
    try:
        text = path.read_text(errors="replace")
        hosts = re.findall(r"^\s*Host\s+(.+)", text, re.MULTILINE)
        if hosts:
            shown = ", ".join(hosts[:4])
            return f"{len(hosts)} host{'s' if len(hosts) != 1 else ''}: {shown}" + (
                "…" if len(hosts) > 4 else ""
            )
    except Exception:
        pass
    return None


def _gitconfig_summary(path: Path) -> Optional[str]:
    """Extract sections from a gitconfig."""
    try:
        text = path.read_text(errors="replace")
        sections = re.findall(r"^\[([^\]]+)\]", text, re.MULTILINE)
        if sections:
            shown = ", ".join(sections[:5])
            return shown + ("…" if len(sections) > 5 else "")
    except Exception:
        pass
    return None


def _plist_summary(path: Path) -> Optional[str]:
    """Peek at plist — just report the top-level keys."""
    try:
        with open(path, "rb") as f:
            data = plistlib.load(f)
        if isinstance(data, dict):
            keys = list(data.keys())
            shown = ", ".join(str(k) for k in keys[:5])
            return f"{len(keys)} keys: {shown}" + ("…" if len(keys) > 5 else "")
    except Exception:
        pass
    return None


def _ini_summary(path: Path, max_sections: int = 5) -> Optional[str]:
    """Extract INI-style section headers."""
    try:
        sections = []
        for line in path.read_text(errors="replace").splitlines():
            m = re.match(r"^\[([^\]]+)\]", line.strip())
            if m:
                sections.append(m.group(1))
            if len(sections) >= max_sections:
                break
        if sections:
            shown = ", ".join(sections[:max_sections])
            return shown + ("…" if len(sections) >= max_sections else "")
    except Exception:
        pass
    return None


# (pattern, label, summary_extractor)
# Patterns are matched against the file's path string (relative or absolute).
KNOWN_CONFIGS: List[Tuple[str, str, Any]] = [
    (".zshrc",                  "Zsh shell config (login shell)",              _shell_summary),
    (".zshenv",                 "Zsh shell env (always sourced)",               _shell_summary),
    (".zprofile",               "Zsh shell profile",                            _shell_summary),
    (".profile",                "Generic shell profile",                        _shell_summary),
    (".bash_profile",           "Bash shell profile",                           _shell_summary),
    (".bashrc",                 "Bash shell config",                            _shell_summary),
    (".tcshrc",                 "Tcsh shell config",                            _shell_summary),
    (".gitconfig",              "Git identity & settings",                      _gitconfig_summary),
    (".npmrc",                  "NPM package manager config",                   _env_summary),
    (".docker/",                "Docker configuration",                         None),
    (".ssh/",                   "SSH keys & config",                            _ssh_config_summary),
    (".hermes/",                "Hermes Agent configuration",                   None),
    (".claude/",                "Claude Code configuration",                    None),
    (".claude.json",            "Claude Code settings",                         _first_json_keys),
    (".cursor/",                "Cursor editor configuration",                  None),
    (".vscode/",                "VS Code settings/",                            None),
    ("config.yaml",             "YAML config",                                  _first_yaml_keys),
    ("config.yml",              "YAML config",                                  _first_yaml_keys),
    ("config.json",             "JSON config",                                  _first_json_keys),
    ("config.toml",             "TOML config",                                  _first_toml_keys),
    (".env",                    "Environment variables",                        _env_summary),
    (".env.",                   "Environment variables",                        _env_summary),
    ("settings.json",           "Application settings (JSON)",                  _first_json_keys),
    ("preferences.json",        "Application preferences (JSON)",              _first_json_keys),
    (".orbstack/",              "OrbStack (Docker replacement)",                None),
    (".openclaw/",              "OpenClaw AI agent",                            None),
    (".orbit/",                 "Orbit personal assistant",                     None),
    (".perci/",                 "Perci (Electron app)",                         None),
    (".lmstudio/",              "LM Studio local LLM",                          None),
    (".ollama/",                "Ollama local LLM",                             None),
    (".logseq/",                "Logseq knowledge base",                        None),
    (".obsidian-cli.sock",      "Obsidian CLI socket",                          None),
    (".gk",                     "GitKraken client",                             None),
    (".gitkraken/",             "GitKraken client",                             None),
    (".codex/",                 "OpenAI Codex CLI",                             None),
    (".continue/",              "Continue.dev (VS Code)",                       None),
    (".cline/",                 "Cline (VS Code agent)",                        None),
    (".copilot/",               "GitHub Copilot",                               None),
    (".gemini/",                "Google Gemini CLI",                            None),
    (".aionui",                 "AI One UI config",                             None),
    (".agents/",                "Agents directory",                             None),
    (".autoforge/",             "Autoforge",                                    None),
    (".vibe/",                  "Vibe coding tool",                             None),
    (".trae/",                  "Trae IDE",                                     None),
    (".securecoder/",           "SecureCoder",                                  None),
    (".antigravity/",           "Antigravity IDE",                              None),
    (".commandcode/",           "CommandCode",                                  None),
    (".aibom/",                 "AI BOM tool",                                  None),
    (".dendron/",               "Dendron knowledge base",                       None),
    (".mempalace/",             "MemPalace memory store",                       None),
    (".graphify/",              "Graphify knowledge graph",                     None),
    (".hyperframes/",           "Hyperframes",                                  None),
    (".openbb_platform/",       "OpenBB Platform (finance)",                    None),
    (".streamlit/",             "Streamlit config",                             None),
    (".matplotlib/",            "Matplotlib config",                            None),
    (".cups/",                  "macOS printing system (CUPS)",                 None),
    (".cargo/",                 "Rust Cargo package manager",                   None),
    (".rustup/",                "Rust toolchain manager",                       None),
    (".bun/",                   "Bun JS runtime",                               None),
    (".npm/",                   "NPM cache/config",                             None),
    (".local/",                 "User-local data",                              None),
    (".cache/",                 "User cache directory",                         None),
    (".py/",                    "Python bytecode cache",                        None),
]


def classify(path: Path) -> Tuple[str, Optional[Any]]:
    """Return (label, summary_extractor) for a given path."""
    rel = str(path)
    for pattern, label, extractor in KNOWN_CONFIGS:
        if pattern in rel:
            return label, extractor
    return None, None


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

# Directories to skip entirely (noise / huge / binary)
SKIP_DIRS = {
    "__pycache__", "node_modules", ".git", "Cache", "Caches",
    "Code Cache", "GPUCache", "Service Worker", "Crash Reports",
    "logs", "tmp", "cache", "CachedData", "Code Cache",
    "DawnCache", "GrShaderCache", "ShaderCache",
    "extensions", "CachedExtensionVSIXs", "CachedProfilesData",
    "Code Storage", "Network Persistent State", "Session Storage",
    "Sessions", "shared_blob", "blob_storage", "VideoCapture",
    "GPUCache", "optimization_cache", "model_cache",
    "node_modules.connector", "packages", "out", "dist",
    "media", "images", "assets", "fonts",
    "site-packages", "conda", "miniconda", "anaconda",
    "venv", "envs", "virtualenvs", ".venv",
    "pkgs", "conda-meta", "share",
}

# Dotdirs that are mostly cache/data/models — only scan top-level files, don't recurse
SHALLOW_DOTDIRS = {
    ".hermes", ".vscode", ".cursor", ".openclaw", ".claude",
    ".claude-science", ".claude-agent",
    ".cache", ".npm", ".cargo", ".rustup", ".bun", ".local",
    ".cups", ".matplotlib", ".streamlit", ".pytest_cache",
    ".agent-browser", ".abacusai-chromium-profile",
    ".lmstudio", ".gemini", ".codex", ".antigravity", ".antigravity-ide",
    ".trae", ".supacode", ".orbit", ".autoforge", ".copilot",
    ".openclaude", ".opalcode", ".securecoder", ".aionui", ".commandcode",
    ".vibe", ".aibom", ".logseq", ".dendron", ".mempalace", ".graphify",
    ".hyperframes", ".openbb_platform", ".gk", ".gitkraken",
    ".ssh", ".docker", ".orbstack",
    ".continue", ".cline", ".abacusai",
}

# Maximum file size to read/line-count (5 MB) — anything larger just shows size+format
MAX_READ_SIZE = 5 * 1024 * 1024

# File extensions to skip (binary / non-config)
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".svg",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".pyc", ".pyo", ".class", ".o", ".a",
    ".db", ".sqlite", ".sqlite3", ".lock",
    ".sock",
}

# Dotfiles/dirs to always skip at top level
SKIP_DOTFILES = {
    ".DS_Store", ".Trash", ".cache", ".local", ".npm", ".cargo",
    ".rustup", ".bun", ".py", ".pytest_cache", ".cups",
    ".bash_history", ".zsh_history", ".zcompdump",
    ".bash_sessions", ".zsh_sessions", ".viminfo",
    ".CFUserTextEncoding", ".electron-gyp", ".swiftpm",
    ".u2net", ".pdf-toolkit-files",
    ".claude.json.backup", ".lmstudio-home-pointer",
    ".obsidian-cli.sock",
}


def discover_files(
    roots: List[Path],
    include_dotfiles: bool = True,
    include_config: bool = True,
) -> List[Path]:
    """Walk the given roots and return a sorted list of config files."""
    files: List[Path] = []

    if include_config:
        config_root = HOME / ".config"
        if config_root.exists():
            for dirpath, dirnames, filenames in os.walk(config_root):
                # prune skip dirs in-place
                dirnames[:] = sorted(
                    d for d in dirnames if d not in SKIP_DIRS
                )
                for fn in sorted(filenames):
                    fp = Path(dirpath) / fn
                    if fp.suffix.lower() in SKIP_EXTENSIONS:
                        continue
                    files.append(fp)

    if include_dotfiles:
        for entry in sorted(HOME.iterdir()):
            name = entry.name
            if name in SKIP_DOTFILES:
                continue
            if name.startswith(".") and not name.startswith(".."):
                if entry.is_file():
                    if entry.suffix.lower() in SKIP_EXTENSIONS:
                        continue
                    files.append(entry)
                elif entry.is_dir() and name not in SKIP_DOTFILES:
                    # For shallow dotdirs, only scan top-level files (no recursion)
                    if name.lower() in SHALLOW_DOTDIRS:
                        for child in sorted(entry.iterdir()):
                            if child.is_file():
                                if child.suffix.lower() in SKIP_EXTENSIONS:
                                    continue
                                files.append(child)
                    else:
                        # walk the dotdir recursively
                        for dirpath, dirnames, filenames in os.walk(entry):
                            dirnames[:] = sorted(
                                d for d in dirnames if d not in SKIP_DIRS
                            )
                            for fn in sorted(filenames):
                                fp = Path(dirpath) / fn
                                if fp.suffix.lower() in SKIP_EXTENSIONS:
                                    continue
                                files.append(fp)

    # deduplicate and sort
    seen = set()
    unique = []
    for f in files:
        resolved = f.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(f)
    unique.sort(key=lambda p: str(p))
    return unique


# ---------------------------------------------------------------------------
# File info extraction
# ---------------------------------------------------------------------------

def human_size(n: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def detect_format(path: Path) -> str:
    """Detect config format from extension / filename."""
    name = path.name.lower()
    suffix = path.suffix.lower()
    mapping = {
        ".json": "JSON",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".toml": "TOML",
        ".ini": "INI",
        ".cfg": "INI",
        ".conf": "CONF",
        ".env": "ENV",
        ".plist": "PLIST",
        ".xml": "XML",
        ".sh": "SHELL",
        ".zsh": "SHELL",
        ".bash": "SHELL",
        ".fish": "SHELL",
        ".py": "PYTHON",
        ".js": "JS",
        ".ts": "TS",
        ".cjs": "JS",
        ".mjs": "JS",
        ".md": "MARKDOWN",
        ".lock": "LOCK",
    }
    if name == ".gitconfig" or name.endswith("config") and suffix == "":
        return "GITCONFIG"
    if name.startswith(".env"):
        return "ENV"
    if name in ("config", "settings", "preferences"):
        return "CONF"
    return mapping.get(suffix, "TEXT")


def count_lines(path: Path) -> Optional[int]:
    """Count lines in a text file; return None on binary/read error."""
    try:
        # fast line count
        count = 0
        with open(path, "rb") as f:
            for _ in f:
                count += 1
        return count
    except Exception:
        return None


def get_summary(path: Path, extractor: Optional[Any]) -> Optional[str]:
    """Get a type-specific summary string for the file."""
    if extractor is not None:
        try:
            result = extractor(path)
            if result:
                return result
        except Exception:
            pass
    # fallback heuristics based on format
    fmt = detect_format(path)
    if fmt == "JSON":
        return _first_json_keys(path)
    if fmt in ("YAML",):
        return _first_yaml_keys(path)
    if fmt == "TOML":
        return _first_toml_keys(path)
    if fmt == "ENV":
        return _env_summary(path)
    if fmt == "PLIST":
        return _plist_summary(path)
    if fmt == "INI":
        return _ini_summary(path)
    if fmt == "GITCONFIG":
        return _gitconfig_summary(path)
    if fmt == "SHELL":
        return _shell_summary(path)
    return None


def file_info(path: Path) -> Optional[Dict[str, Any]]:
    """Collect all info about a config file."""
    try:
        stat = path.stat()
    except Exception:
        return None

    size = stat.st_size
    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
    fmt = detect_format(path)
    lines = count_lines(path) if size <= MAX_READ_SIZE else None  # skip huge files
    label, extractor = classify(path)
    summary = get_summary(path, extractor) if size <= MAX_READ_SIZE else None

    return {
        "path": path,
        "size": size,
        "size_human": human_size(size),
        "mtime": mtime,
        "format": fmt,
        "lines": lines,
        "label": label or "",
        "summary": summary or "",
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def make_table_for_group(group_name: str, items: List[Dict]) -> Table:
    """Build a rich Table for a group of config files."""
    table = Table(
        title=f"[bold cyan]{group_name}[/bold cyan]  [dim]({len(items)} file{'s' if len(items) != 1 else ''})[/dim]",
        box=box.ROUNDED,
        show_lines=False,
        title_style="bold",
        border_style="bright_black",
        pad_edge=True,
        expand=True,
    )
    table.add_column("File", style="bold white", no_wrap=True, max_width=40)
    table.add_column("Format", style="magenta", justify="center", max_width=10)
    table.add_column("Size", style="green", justify="right", max_width=8)
    table.add_column("Lines", style="yellow", justify="right", max_width=7)
    table.add_column("Modified", style="dim", max_width=16)
    table.add_column("Purpose / Summary", style="italic white", ratio=2, no_wrap=False)

    for item in items:
        rel = str(item["path"]).replace(str(HOME), "~")
        # shorten if too long
        if len(rel) > 50:
            rel = "…" + rel[-49:]

        lines_str = f"{item['lines']:,}" if item["lines"] is not None else "—"
        summary_parts = []
        if item["label"]:
            summary_parts.append(f"[dim]{item['label']}[/dim]")
        if item["summary"]:
            summary_parts.append(f"[italic]{item['summary']}[/italic]")
        summary = "  •  ".join(summary_parts) if summary_parts else "—"

        table.add_row(
            rel,
            item["format"],
            item["size_human"],
            lines_str,
            item["mtime"],
            summary,
        )
    return table


def group_by_parent(items: List[Dict]) -> OrderedDict:
    """Group items by their parent directory."""
    groups = OrderedDict()
    for item in items:
        parent = str(item["path"].parent).replace(str(HOME), "~")
        if parent not in groups:
            groups[parent] = []
        groups[parent].append(item)
    return groups


def render_full_report(
    items: List[Dict],
    console: Console,
    title: str = "Config Map",
):
    """Render the full beautiful report."""
    # Header
    console.print()
    console.print(
        Rule(
            title=f"[bold white] {title} [/bold white]",
            style="bold cyan",
            align="center",
        )
    )
    console.print(
        f"[dim]  Scanned [bold]{len(items)}[/bold] config files  •  "
        f"[bold]{datetime.now().strftime('%Y-%m-%d %H:%M')}[/bold][/dim]"
    )
    console.print()

    groups = group_by_parent(items)

    # Summary stats
    total_size = sum(i["size"] for i in items)
    formats: Dict[str, int] = {}
    for i in items:
        formats[i["format"]] = formats.get(i["format"], 0) + 1

    fmt_summary = ", ".join(
        f"[bold]{k}[/bold] [dim]({v})[/dim]" for k, v in sorted(formats.items(), key=lambda x: -x[1])
    )

    stats = Table.grid(padding=(0, 2))
    stats.add_column(style="dim", justify="right")
    stats.add_column(style="white")
    stats.add_row("Total files:", f"[bold]{len(items)}[/bold]")
    stats.add_row("Total size:", f"[bold]{human_size(total_size)}[/bold]")
    stats.add_row("Formats:", fmt_summary)
    stats.add_row("Directories:", f"[bold]{len(groups)}[/bold]")

    console.print(Panel(stats, title="[bold]Summary[/bold]", border_style="cyan", expand=True))
    console.print()

    # Render each group
    for group_name, group_items in groups.items():
        # sort by size descending within group
        group_items.sort(key=lambda x: -x["size"])
        table = make_table_for_group(group_name, group_items)
        console.print(table)
        console.print()

    console.print(Rule(style="dim"))


def generate_demo_items() -> List[Dict[str, Any]]:
    """Generate synthetic config file data for screenshots. No real filesystem access."""
    from datetime import datetime, timedelta

    now = datetime.now()
    def days_ago(n): return (now - timedelta(days=n)).strftime("%Y-%m-%d %H:%M")

    return [
        {"path": Path("~/.zshrc"), "size": 2764, "size_human": "2.7 KB", "mtime": days_ago(2), "format": "SHELL", "lines": 81, "label": "Zsh shell config (login shell)", "summary": "9 aliases, 21 exports"},
        {"path": Path("~/.zshenv"), "size": 590, "size_human": "590 B", "mtime": days_ago(48), "format": "SHELL", "lines": 12, "label": "Zsh shell env (always sourced)", "summary": "3 exports"},
        {"path": Path("~/.gitconfig"), "size": 412, "size_human": "412 B", "mtime": days_ago(3), "format": "GITCONFIG", "lines": 18, "label": "Git identity & settings", "summary": "user, core, alias, push"},
        {"path": Path("~/.ssh/config"), "size": 690, "size_human": "690 B", "mtime": days_ago(9), "format": "GITCONFIG", "lines": 17, "label": "SSH keys & config", "summary": "2 hosts: prod-web, dev-api"},
        {"path": Path("~/.config/gh/config.yml"), "size": 1280, "size_human": "1.3 KB", "mtime": days_ago(14), "format": "YAML", "lines": 42, "label": "GitHub CLI config", "summary": "editor, prompt, aliases, browser"},
        {"path": Path("~/.config/alacritty/alacritty.toml"), "size": 4200, "size_human": "4.2 KB", "mtime": days_ago(30), "format": "TOML", "lines": 156, "label": "Terminal emulator config", "summary": "font, colors, window, cursor, shell"},
        {"path": Path("~/.config/nvim/init.lua"), "size": 8192, "size_human": "8.2 KB", "mtime": days_ago(5), "format": "TEXT", "lines": 247, "label": "Neovim config (Lua)", "summary": "plugins, keymaps, lsp, treesitter"},
        {"path": Path("~/.config/starship.toml"), "size": 1536, "size_human": "1.5 KB", "mtime": days_ago(60), "format": "TOML", "lines": 52, "label": "Cross-shell prompt", "summary": "character, directory, git_branch, package, time"},
        {"path": Path("~/.config/atuin/config.toml"), "size": 768, "size_human": "768 B", "mtime": days_ago(7), "format": "TOML", "lines": 24, "label": "Shell history DB", "summary": "auto_sync, dialect, search_mode, sync_address"},
        {"path": Path("~/.docker/config.json"), "size": 340, "size_human": "340 B", "mtime": days_ago(120), "format": "JSON", "lines": 8, "label": "Docker client config", "summary": "auths, credsStore, currentContext"},
        {"path": Path(".env"), "size": 1280, "size_human": "1.3 KB", "mtime": days_ago(1), "format": "ENV", "lines": 38, "label": "Environment variables", "summary": "12 variables"},
        {"path": Path("pyproject.toml"), "size": 2048, "size_human": "2.0 KB", "mtime": days_ago(4), "format": "TOML", "lines": 67, "label": "Python project config", "summary": "[project], [build-system], [tool.ruff], [tool.pytest]"},
        {"path": Path("package.json"), "size": 1856, "size_human": "1.9 KB", "mtime": days_ago(2), "format": "JSON", "lines": 52, "label": "Node.js project manifest", "summary": "name, version, scripts, dependencies, devDependencies"},
        {"path": Path(".github/workflows/ci.yml"), "size": 920, "size_human": "920 B", "mtime": days_ago(6), "format": "YAML", "lines": 28, "label": "GitHub Actions CI", "summary": "name, on, jobs, steps, uses, run"},
        {"path": Path("docker-compose.yml"), "size": 1408, "size_human": "1.4 KB", "mtime": days_ago(10), "format": "YAML", "lines": 41, "label": "Docker Compose services", "summary": "version, networks, volumes, build, ports, env_file"},
        {"path": Path("Cargo.toml"), "size": 1024, "size_human": "1.0 KB", "mtime": days_ago(15), "format": "TOML", "lines": 35, "label": "Rust package manifest", "summary": "[package], [dependencies], [features], [profile.release]"},
        {"path": Path("~/.aws/credentials"), "size": 256, "size_human": "256 B", "mtime": days_ago(90), "format": "INI", "lines": 6, "label": "AWS credentials", "summary": "[default], [staging]"},
        {"path": Path("~/.config/1Password/ssh/agent.toml"), "size": 180, "size_human": "180 B", "mtime": days_ago(45), "format": "TOML", "lines": 5, "label": "1Password SSH agent", "summary": "ssh_keys, allowed_buckets"},
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Beautiful terminal map of your configuration files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--demo", action="store_true", help="Render with synthetic data (for screenshots)")
    parser.add_argument("--dotfiles", action="store_true", help="Only scan top-level dotfiles")
    parser.add_argument("--config", action="store_true", help="Only scan ~/.config/")
    parser.add_argument("--search", type=str, default=None, help="Filter by path/name substring")
    parser.add_argument(
        "--min-size",
        type=str,
        default=None,
        help="Minimum file size (e.g., '1k', '100b', '1m')",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable colored output")
    interface = parser.add_mutually_exclusive_group()
    interface.add_argument("--interactive", action="store_true", help="Force the interactive TUI")
    interface.add_argument(
        "--no-interactive",
        action="store_true",
        help="Render the static report, even in a terminal",
    )
    args = parser.parse_args()

    console = Console(
        color_system="auto" if not args.no_color else None,
        force_terminal=False if args.no_color else None,
    )

    interactive = not args.no_color and (
        args.interactive
        or (
            not args.no_interactive
            and sys.stdin.isatty()
            and sys.stdout.isatty()
        )
    )

    # ── Demo mode: synthetic data, no filesystem access ─────────────────
    if args.demo:
        items = generate_demo_items()
        title_parts = ["System Config", f"{len(items)} files"]
        if interactive:
            from config_map.tui import run_tui

            run_tui(items, " • ".join(title_parts), initial_query=args.search or "")
            return
        if args.search:
            needle = args.search.lower()
            items = [i for i in items if needle in str(i["path"]).lower()]
            title_parts.append(f"matching '{args.search}'")
        render_full_report(items, console, title=" • ".join(title_parts))
        return

    # ── Real mode: scan filesystem ─────────────────────────────────────
    if args.dotfiles and args.config:
        sys.stderr.write("[ERROR] --dotfiles and --config are mutually exclusive\n")
        sys.exit(1)
    include_dotfiles = not args.config
    include_config = not args.dotfiles

    files = discover_files(
        roots=[],
        include_dotfiles=include_dotfiles,
        include_config=include_config,
    )

    items = []
    total = len(files)
    with console.status(f"[bold cyan]Analyzing 0/{total} files…[/bold cyan]", spinner="dots") as status:
        for idx, fp in enumerate(files, 1):
            if idx % 50 == 0 or idx == total:
                status.update(f"[bold cyan]Analyzing {idx}/{total} files…[/bold cyan]")
            info = file_info(fp)
            if info:
                items.append(info)

    # Apply filters. In the TUI, --search seeds the editable live filter.
    if args.search and not interactive:
        needle = args.search.lower()
        items = [i for i in items if needle in str(i["path"]).lower()]

    min_bytes = None
    if args.min_size:
        size_str = args.min_size.lower().strip()
        multipliers = {"b": 1, "k": 1024, "kb": 1024, "m": 1024**2, "mb": 1024**2, "g": 1024**3}
        m = re.match(r"^(\d+(?:\.\d+)?)\s*([a-z]*)$", size_str)
        if m:
            num = float(m.group(1))
            unit = m.group(2) or "b"
            min_bytes = int(num * multipliers.get(unit, 1))
            items = [i for i in items if i["size"] >= min_bytes]
        else:
            sys.stderr.write(f"[WARN] Could not parse --min-size '{args.min_size}', ignoring\n")

    if not items:
        console.print("[yellow]No config files found matching criteria.[/yellow]")
        sys.exit(0)

    title_parts = []
    if args.dotfiles:
        title_parts.append("Dotfiles")
    elif args.config:
        title_parts.append("~/.config")
    else:
        title_parts.append("System Config")
    if args.search and not interactive:
        title_parts.append(f"matching '{args.search}'")
    if args.min_size:
        title_parts.append(f">= {args.min_size}")

    title = " • ".join(title_parts)
    if interactive:
        from config_map.tui import run_tui

        def refresh_items() -> List[Dict[str, Any]]:
            refreshed = []
            for path in discover_files(
                roots=[],
                include_dotfiles=include_dotfiles,
                include_config=include_config,
            ):
                info = file_info(path)
                if info and (min_bytes is None or info["size"] >= min_bytes):
                    refreshed.append(info)
            return refreshed

        run_tui(items, title, initial_query=args.search or "", refresh_callback=refresh_items)
    else:
        with console.pager():
            render_full_report(items, console, title=title)


if __name__ == "__main__":
    main()
