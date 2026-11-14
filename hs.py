#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pymobiledevice3>=11.54"]
# ///
"""Read, edit and write back an iPhone Home Screen layout over USB.

    ./hs.py pull              phone -> layout.txt
    ./hs.py apply             layout.txt -> phone (backs up first)
    ./hs.py backup            phone -> backups/
    ./hs.py restore [FILE]    newest backup (or FILE) -> phone
    ./hs.py data              print the folder the files above live in
    ./hs.py test              self-check, no phone needed
"""
import argparse
import asyncio
import difflib
import os
import plistlib
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def data_dir(here=HERE, env=os.environ):
    """Folder for layout.txt, plan.txt and backups/: $HS_DATA, else next to this file.

    Installed as a Claude Code plugin this file sits in a cache that every update replaces,
    so there the data goes to the home folder instead.
    """
    if env.get("HS_DATA"):
        return Path(env["HS_DATA"]).expanduser()
    if "/.claude/plugins/" in here.as_posix() + "/":
        return Path.home() / "iphone-homescreen-data"
    return here


DATA = data_dir()
LAYOUT = DATA / "layout.txt"
BACKUPS = DATA / "backups"

# iPhone: 6 rows x 4, dock 4, folder 3 x 3. Other devices set HS_GRID, e.g. "30,12,16" for an iPad (6 x 5, folder 4 x 4).
PAGE_SLOTS, DOCK_SLOTS, FOLDER_PAGE_SLOTS = map(int, os.environ.get("HS_GRID", "24,4,9").split(","))
WIDGET_SLOTS = {"small": 4, "medium": 8, "large": 16}
SEP = " | "


class LayoutError(Exception):
    pass


# ---------- layout <-> text ----------

def is_folder(item):
    return item.get("listType") == "folder"


def line(item):
    if item.get("iconType") == "custom":
        label = f"[widget {item.get('gridSize')}] {item.get('widgetIdentifier') or item.get('bundleIdentifier')}"
    else:
        label = item.get("displayName") or item.get("bundleIdentifier") or "?"
    return f"{label}{SEP}{item['displayIdentifier']}"


def render(state):
    out = []
    for n, page in enumerate(state):
        out.append("== Dock" if n == 0 else f"== Page {n}")
        for item in page:
            if not is_folder(item):
                out.append(line(item))
                continue
            out.append(f"Folder: {item.get('displayName', '')}")
            for k, folder_page in enumerate(item["iconLists"]):
                if k:
                    out.append("    --")
                out += [f"    {line(x)}" for x in folder_page]
        out.append("")
    return "\n".join(out)


def parse(text):
    """Text -> pages. An entry is an identifier (str) or {"name", "pages": [[id, ...], ...]}."""
    pages, folder = [], None
    for no, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("=="):
            pages.append([])
            folder = None
        elif not pages:
            raise LayoutError(f"line {no}: item before the first '==' heading")
        elif s.startswith("Folder:"):
            folder = {"name": s[len("Folder:"):].strip(), "pages": [[]]}
            pages[-1].append(folder)
        elif raw[0] in " \t":
            if folder is None:
                raise LayoutError(f"line {no}: indented line outside a folder")
            if s == "--":
                folder["pages"].append([])
            else:
                folder["pages"][-1].append(s.rsplit(SEP, 1)[-1])
        else:
            folder = None
            pages[-1].append(s.rsplit(SEP, 1)[-1])
    return pages


def index(state):
    """identifier -> the phone's own record for every app, web clip and widget."""
    found = {}
    for page in state:
        for item in page:
            if is_folder(item):
                for folder_page in item["iconLists"]:
                    found.update((x["displayIdentifier"], x) for x in folder_page)
            else:
                found[item["displayIdentifier"]] = item
    return found


def build(pages, current):
    """Parsed text + the phone's current state -> a new state, or LayoutError listing every problem."""
    known, used, errors = index(current), Counter(), []

    def take(ident):
        used[ident] += 1
        if ident not in known:
            errors.append(f"not on the phone: {ident}")
        return known.get(ident, {})

    def slots(items):
        return sum(WIDGET_SLOTS.get(i.get("gridSize"), 1) for i in items)

    state = []
    for n, page in enumerate(pages):
        where = "Dock" if n == 0 else f"Page {n}"
        items = []
        for entry in page:
            if isinstance(entry, str):
                items.append(take(entry))
                continue
            lists = [[take(i) for i in fp] for fp in entry["pages"] if fp]
            if not lists:
                errors.append(f"{where}: folder '{entry['name']}' is empty")
            for fp in lists:
                if any("gridSize" in i for i in fp):
                    errors.append(f"{where}: folder '{entry['name']}' contains a widget")
                if len(fp) > FOLDER_PAGE_SLOTS:
                    errors.append(f"{where}: folder '{entry['name']}' has a page with {len(fp)} items, max {FOLDER_PAGE_SLOTS}")
            items.append({"displayName": entry["name"], "iconLists": lists, "listType": "folder"})
        limit = DOCK_SLOTS if n == 0 else PAGE_SLOTS
        same = n < len(current) and render([items]) == render([current[n]])  # a page left as the device has it is valid
        if slots(items) > limit and not same:
            errors.append(f"{where}: {slots(items)} slots used, max {limit}")
        state.append(items)

    errors += [f"listed {c} times: {i}" for i, c in used.items() if c > 1]
    missing = [line(known[i]) for i in known if i not in used]
    if missing:  # iOS puts left-out apps back itself, and drags App Library apps out with them
        errors.append(
            f"{len(missing)} item(s) on the phone are not in the file (add them back):\n    "
            + "\n    ".join(missing)
        )
    if errors:
        raise LayoutError("\n".join(errors))
    return state


# ---------- phone ----------

async def springboard():
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.springboard import SpringBoardServicesService

    return SpringBoardServicesService(lockdown=await create_using_usbmux())


async def get_state():
    return await (await springboard()).get_icon_state()


async def set_state(state):
    await (await springboard()).set_icon_state(state)
    await asyncio.sleep(3)  # SpringBoard needs a moment before a read reflects the write


def save_backup(state):
    BACKUPS.mkdir(parents=True, exist_ok=True)
    path = BACKUPS / f"{datetime.now():%Y-%m-%d-%H%M%S}.plist"
    path.write_bytes(plistlib.dumps(state))
    return path


async def write_and_verify(new):
    current = await get_state()
    if render(current) == render(new):
        print("Phone already matches. Nothing sent.")
        return
    backup = save_backup(current)
    print(f"Backup: {backup}")
    await set_state(new)
    after = render(await get_state())
    if after == render(new):
        print("Applied and verified.")
        return
    print("The phone's layout differs from what was sent:")
    print("\n".join(difflib.unified_diff(render(new).splitlines(), after.splitlines(), "sent", "phone", lineterm="", n=1)))
    sys.exit(f"To undo: ./hs.py restore {backup}")


# ---------- commands ----------

async def cmd_pull(args):
    DATA.mkdir(parents=True, exist_ok=True)
    LAYOUT.write_text(render(await get_state()))
    print(f"Wrote {LAYOUT}")


async def cmd_apply(args):
    await write_and_verify(build(parse(LAYOUT.read_text()), await get_state()))


async def cmd_backup(args):
    print(f"Backup: {save_backup(await get_state())}")


async def cmd_restore(args):
    path = Path(args.file) if args.file else max(BACKUPS.glob("*.plist"), default=None)
    if path is None:
        sys.exit(f"No backups in {BACKUPS}")
    print(f"Restoring {path}")
    await write_and_verify(plistlib.loads(path.read_bytes()))


async def cmd_data(args):
    print(DATA)


async def cmd_test(args):
    home_data = Path.home() / "iphone-homescreen-data"
    assert data_dir(Path("/x/tool"), {}) == Path("/x/tool")
    assert data_dir(Path("/x/.claude/plugins/cache/m/p/1"), {}) == home_data
    assert data_dir(Path("/x/.claude/plugins/cache/m/p/1"), {"HS_DATA": "/y"}) == Path("/y")

    app = lambda i: {"displayIdentifier": i, "displayName": i.upper()}
    widget = {"displayIdentifier": "W-1", "iconType": "custom", "gridSize": "small", "widgetIdentifier": "w", "iconLists": []}
    folder = {"displayName": "Stuff | more", "iconLists": [[app("c"), app("d")], [app("e")]], "listType": "folder"}
    state = [[app("a")], [app("b"), widget, folder], [app("f")]]

    assert build(parse(render(state)), state) == state, "round trip changed the layout"

    def problem(text):
        try:
            build(parse(text), state)
        except LayoutError as e:
            return str(e)
        return ""

    full = render(state)
    assert "listed 2 times" in problem(full + "\n== Page 3\nx | a\n")
    assert "not on the phone" in problem(full + "\n== Page 3\nx | zzz\n")
    assert "not in the file" in problem(full.replace("F | f\n", ""))
    assert "slots used, max 4" in problem("== Dock\n" + "\n".join(f"x | {i}" for i in "abcdef") + "\nw | W-1\n")
    print("ok")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pull").set_defaults(fn=cmd_pull)
    sub.add_parser("apply").set_defaults(fn=cmd_apply)
    sub.add_parser("backup").set_defaults(fn=cmd_backup)
    r = sub.add_parser("restore")
    r.add_argument("file", nargs="?")
    r.set_defaults(fn=cmd_restore)
    sub.add_parser("data").set_defaults(fn=cmd_data)
    sub.add_parser("test").set_defaults(fn=cmd_test)
    args = p.parse_args()
    try:
        asyncio.run(args.fn(args))
    except LayoutError as e:
        sys.exit(f"Layout not applied:\n{e}")


if __name__ == "__main__":
    main()
