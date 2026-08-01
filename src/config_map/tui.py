"""Interactive terminal interface for config-map."""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Input, Static


Item = Dict[str, Any]
RefreshCallback = Callable[[], List[Item]]
SORT_MODES = ("path", "size", "modified")


def filter_items(items: List[Item], query: str) -> List[Item]:
    """Return items matching every whitespace-separated search term."""
    terms = query.casefold().split()
    if not terms:
        return list(items)

    matches = []
    for item in items:
        searchable = " ".join(
            str(item.get(field, ""))
            for field in ("path", "format", "label", "summary")
        ).casefold()
        if all(term in searchable for term in terms):
            matches.append(item)
    return matches


def sort_items(items: List[Item], mode: str) -> List[Item]:
    """Sort items for display without mutating the scan result."""
    if mode == "size":
        return sorted(items, key=lambda item: (-item["size"], str(item["path"]).casefold()))
    if mode == "modified":
        return sorted(items, key=lambda item: (item["mtime"], str(item["path"]).casefold()), reverse=True)
    return sorted(items, key=lambda item: str(item["path"]).casefold())


class ConfigMapApp(App[None]):
    """Searchable, sortable browser for scanned configuration files."""

    TITLE = "config-map"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen {
        background: #090d18;
        color: #e5e7eb;
        layout: vertical;
    }

    #masthead {
        height: 3;
        padding: 1 2 0 2;
        background: #101827;
        color: #f8fafc;
        text-style: bold;
    }

    #search {
        height: 3;
        margin: 0 1;
        border: tall #334155;
        background: #111827;
    }

    #search:focus {
        border: tall #22d3ee;
    }

    #stats {
        height: 2;
        padding: 0 2;
        color: #94a3b8;
    }

    #files {
        height: 1fr;
        margin: 0 1;
        background: #0f172a;
        border: round #263449;
    }

    #files > .datatable--header {
        background: #172033;
        color: #67e8f9;
        text-style: bold;
    }

    #files > .datatable--cursor {
        background: #155e75;
        color: #ffffff;
        text-style: bold;
    }

    #detail {
        height: 7;
        margin: 0 1;
        padding: 1 2;
        border: round #263449;
        background: #101827;
        color: #cbd5e1;
    }

    Footer {
        background: #101827;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("/", "focus_search", "Search"),
        Binding("escape", "clear_search", "Clear"),
        Binding("s", "cycle_sort", "Sort"),
        Binding("r", "refresh_files", "Refresh"),
        Binding("j", "move_cursor(1)", "Down", show=False),
        Binding("k", "move_cursor(-1)", "Up", show=False),
    ]

    def __init__(
        self,
        items: List[Item],
        title: str,
        initial_query: str = "",
        refresh_callback: Optional[RefreshCallback] = None,
    ) -> None:
        super().__init__()
        self.items = list(items)
        self.visible_items: List[Item] = []
        self.report_title = title
        self.initial_query = initial_query
        self.refresh_callback = refresh_callback
        self.sort_mode = "path"

    def compose(self) -> ComposeResult:
        yield Static(Text(self.report_title, style="bold"), id="masthead")
        yield Input(
            value=self.initial_query,
            placeholder="Search paths, formats, purposes, and summaries…",
            id="search",
        )
        yield Static(id="stats")
        yield DataTable(id="files")
        yield Static(id="detail")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#files", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_column("File", width=38)
        table.add_column("Format", width=10)
        table.add_column("Size", width=10)
        table.add_column("Lines", width=8)
        table.add_column("Modified", width=17)
        table.add_column("Purpose / Summary", width=48)
        self.refresh_table()
        table.focus()

    def refresh_table(self) -> None:
        """Rebuild the table from the current query and sort mode."""
        query = self.query_one("#search", Input).value
        self.visible_items = sort_items(filter_items(self.items, query), self.sort_mode)

        table = self.query_one("#files", DataTable)
        table.clear()
        for item in self.visible_items:
            path = str(item["path"]).replace(str(Path.home()), "~")
            lines = f"{item['lines']:,}" if item["lines"] is not None else "—"
            purpose = " • ".join(part for part in (item["label"], item["summary"]) if part) or "—"
            table.add_row(
                path,
                item["format"],
                item["size_human"],
                lines,
                item["mtime"],
                purpose,
                key=str(item["path"]),
            )

        stats = Text()
        stats.append(f"{len(self.visible_items)}", style="bold cyan")
        stats.append(f" of {len(self.items)} files  •  sort: ")
        stats.append(self.sort_mode, style="bold magenta")
        if query:
            stats.append("  •  live filter active", style="yellow")
        self.query_one("#stats", Static).update(stats)

        if self.visible_items:
            table.move_cursor(row=0)
            self.update_detail(self.visible_items[0])
        else:
            self.query_one("#detail", Static).update(
                Text("No files match this search. Press Esc to clear it.", style="yellow")
            )

    def update_detail(self, item: Item) -> None:
        detail = Text()
        detail.append(str(item["path"]).replace(str(Path.home()), "~"), style="bold white")
        detail.append("\n")
        detail.append(item["label"] or "Unclassified configuration", style="cyan")
        if item["summary"]:
            detail.append(f"  •  {item['summary']}", style="italic")
        detail.append("\n")
        detail.append(
            f"{item['format']}  •  {item['size_human']}  •  "
            f"{item['lines'] if item['lines'] is not None else '—'} lines  •  modified {item['mtime']}",
            style="dim",
        )
        self.query_one("#detail", Static).update(detail)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search" and self.is_mounted:
            self.refresh_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#files", DataTable).focus()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if 0 <= event.cursor_row < len(self.visible_items):
            self.update_detail(self.visible_items[event.cursor_row])

    def action_focus_search(self) -> None:
        search = self.query_one("#search", Input)
        search.focus()
        search.cursor_position = len(search.value)

    def action_clear_search(self) -> None:
        search = self.query_one("#search", Input)
        if search.value:
            search.value = ""
        self.query_one("#files", DataTable).focus()

    def action_cycle_sort(self) -> None:
        index = (SORT_MODES.index(self.sort_mode) + 1) % len(SORT_MODES)
        self.sort_mode = SORT_MODES[index]
        self.refresh_table()

    def action_move_cursor(self, amount: int) -> None:
        table = self.query_one("#files", DataTable)
        if not self.visible_items:
            return
        row = max(0, min(table.cursor_row + amount, len(self.visible_items) - 1))
        table.move_cursor(row=row)

    def action_refresh_files(self) -> None:
        if self.refresh_callback is None:
            self.notify("Refresh is unavailable for synthetic data.")
            return
        self.notify("Rescanning configuration files…")
        self.refresh_in_background()

    @work(thread=True, exclusive=True)
    def refresh_in_background(self) -> None:
        """Rescan without blocking keyboard and mouse input."""
        try:
            items = self.refresh_callback() if self.refresh_callback else []
        except Exception as error:
            self.call_from_thread(
                self.notify,
                f"Refresh failed: {error}",
                severity="error",
            )
            return
        self.call_from_thread(self.finish_refresh, items)

    def finish_refresh(self, items: List[Item]) -> None:
        self.items = items
        self.refresh_table()
        self.notify(f"Rescanned {len(self.items)} files.")


def run_tui(
    items: List[Item],
    title: str,
    initial_query: str = "",
    refresh_callback: Optional[RefreshCallback] = None,
) -> None:
    """Run the full-screen config-map interface."""
    ConfigMapApp(items, title, initial_query, refresh_callback).run()
