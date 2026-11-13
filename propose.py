"""Build layout.proposed.txt from the grouping plan in plan.txt. Offline: reads the newest backup, never the phone.

    python3 propose.py
"""
import sys, plistlib, pathlib, importlib.util
REPO = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("hs", REPO / "hs.py"); hs = importlib.util.module_from_spec(spec); spec.loader.exec_module(hs)

PLAN_FILE = hs.DATA / "plan.txt"
if not PLAN_FILE.exists():
    sys.exit(f"No plan.txt yet. Copy {REPO / 'plan.example.txt'} to {PLAN_FILE} and fill it in.")
PLAN = PLAN_FILE.read_text()
keep = [l.split()[2] for l in PLAN.splitlines() if l.startswith("@ Keep ")]
KEEP_PAGES = int(keep[0]) if keep else 1   # pages after the dock copied from the phone unchanged

newest = max(hs.BACKUPS.glob("*.plist"), default=None)
if newest is None:
    sys.exit("No backup yet. Run ./hs.py backup first.")
state = plistlib.loads(newest.read_bytes())
norm = lambda s: s.replace("‎", "").strip()
rest = {}                      # id -> item, everything after the kept pages
for page in state[1 + KEEP_PAGES:]:
    for it in page:
        for x in ([y for fp in it["iconLists"] for y in fp] if hs.is_folder(it) else [it]):
            rest[x["displayIdentifier"]] = x
by_name = {}
for i, x in rest.items():
    by_name.setdefault(norm(x.get("displayName") or ""), []).append(i)

used, problems = [], []
def resolve(tok):
    tok = tok.strip()
    if tok.startswith("="):
        i = tok[1:]
        if i not in rest: problems.append(f"unknown id {i}"); return None
    else:
        ids = by_name.get(tok, [])
        if not ids: gone.append(tok); return None
        if len(ids) > 1: problems.append(f"name '{tok}' matches {len(ids)}"); return None
        i = ids[0]
    used.append(i); return i

out = [hs.render(state[:1 + KEEP_PAGES]).rstrip("\n"), ""]
summary = []
gone = []                      # named in the plan, no longer on the phone
for raw in PLAN.strip().splitlines():
    if not raw.strip() or raw.startswith("@ Keep "): continue
    if raw.startswith("@"):
        out += ["", "== " + raw[1:].strip()]; in_folder = False
    elif raw.startswith("#"):
        out.append("Folder: " + raw[1:].strip()); in_folder = True; first = True; summary.append([raw[1:].strip(), 0])
    else:
        ids = [i for i in map(resolve, raw.split(";")) if i]
        if in_folder:
            if not first: out.append("    --")
            first = False
            out += ["    " + hs.line(rest[i]) for i in ids]; summary[-1][1] += len(ids)
        else:
            out += [hs.line(rest[i]) for i in ids]
left = [i for i in rest if i not in used]
room = 0
for i in left:                 # in no folder of the plan yet: own pages at the end, as many as needed
    need = hs.WIDGET_SLOTS.get(rest[i].get("gridSize"), 1)
    if need > room:
        out += ["", "== Not grouped"]; room = hs.PAGE_SLOTS
    out.append(hs.line(rest[i])); room -= need
text = "\n".join(out) + "\n"
dups = {i for i in used if used.count(i) > 1}
print("problems:", problems or "none", "| duplicates:", [hs.line(rest[i]) for i in dups] or "none")
try:
    new = hs.build(hs.parse(text), state)      # raises on any rule broken
except hs.LayoutError as e:
    sys.exit(f"Plan not usable, nothing written:\n{e}")
print('in the plan but not on the phone:', gone or 'none')
(hs.DATA / "layout.proposed.txt").write_text(text)
print("valid. pages:", len(new) - 1, "| items after the kept pages:", len(rest), "| in folders:", sum(n for _, n in summary))
print("page slots:", [sum(hs.WIDGET_SLOTS.get(i.get("gridSize"), 1) for i in p) for p in new])
for name, n in summary: print(f"{n:3} {name}")
print("NOT GROUPED:"); [print("   ", hs.line(rest[i])) for i in left]
