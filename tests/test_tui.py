import asyncio
from pathlib import Path

from config_map.tui import ConfigMapApp, filter_items, sort_items


def make_item(path, size, modified, fmt="TOML", label="", summary=""):
    return {
        "path": Path(path),
        "size": size,
        "size_human": f"{size} B",
        "mtime": modified,
        "format": fmt,
        "lines": 1,
        "label": label,
        "summary": summary,
    }


ITEMS = [
    make_item("~/.config/alpha.toml", 10, "2026-01-01 10:00", summary="theme colors"),
    make_item("~/.config/beta.json", 30, "2026-03-01 10:00", fmt="JSON", label="Beta tool"),
    make_item("~/.zshrc", 20, "2026-02-01 10:00", fmt="SHELL", summary="4 aliases"),
]


def test_filter_searches_all_visible_metadata():
    assert [item["path"] for item in filter_items(ITEMS, "json beta")] == [Path("~/.config/beta.json")]
    assert [item["path"] for item in filter_items(ITEMS, "aliases")] == [Path("~/.zshrc")]


def test_sort_modes_are_deterministic():
    assert sort_items(ITEMS, "size")[0]["size"] == 30
    assert sort_items(ITEMS, "modified")[0]["mtime"] == "2026-03-01 10:00"
    assert sort_items(ITEMS, "path")[0]["path"] == Path("~/.config/alpha.toml")


def test_live_search_and_sort_controls():
    async def run_test():
        app = ConfigMapApp(ITEMS, "Test Config")
        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.press("/")
            await pilot.press("b", "e", "t", "a")
            assert len(app.visible_items) == 1
            assert app.visible_items[0]["path"] == Path("~/.config/beta.json")

            await pilot.press("escape")
            assert len(app.visible_items) == 3
            await pilot.press("s")
            assert app.sort_mode == "size"
            assert app.visible_items[0]["size"] == 30

    asyncio.run(run_test())


def test_background_refresh_replaces_scan_results():
    async def run_test():
        refreshed = [make_item("~/.config/new.toml", 40, "2026-04-01 10:00")]
        app = ConfigMapApp(ITEMS, "Test Config", refresh_callback=lambda: refreshed)
        async with app.run_test(size=(110, 32)) as pilot:
            await pilot.press("r")
            await pilot.pause(0.2)
            assert app.items == refreshed
            assert app.visible_items == refreshed

    asyncio.run(run_test())
