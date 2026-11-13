---
name: iphone-homescreen
description: Use when the user asks to organise, rearrange, group, tidy or back up the apps on their iPhone Home Screen, move an app to a folder or page, create or rename a Home Screen folder, undo a Home Screen change, or says "/iphone-homescreen". Reads and writes the layout from a Mac over a USB cable; no jailbreak, no app on the phone.
---

# Rearrange the iPhone Home Screen

Reads the iPhone's Home Screen layout over USB into a text file, changes it there, and writes it back. Claude does the sorting; the user says how they want it.

## What you need

- A Mac with [`uv`](https://docs.astral.sh/uv/) (`brew install uv`). `uv` fetches the one dependency, `pymobiledevice3`, on first run.
- An iPhone on a USB data cable (not a charge-only cable), unlocked, with "Trust This Computer" accepted.
- Tested on iOS 27.2 with an iPhone 16. The page size in `hs.py` (6 rows of 4) is the iPhone grid; an iPad needs other numbers.

## Install

As a Claude Code plugin:

```
claude plugin marketplace add MaurizioJJ/iphone-homescreen-skill
claude plugin install iphone-homescreen@iphone-homescreen-skill
```

Or from a clone, which also gives the scripts to use by hand:

```
git clone https://github.com/MaurizioJJ/iphone-homescreen-skill ~/iphone-homescreen
ln -s ~/iphone-homescreen/skills/iphone-homescreen ~/.claude/skills/iphone-homescreen
cd ~/iphone-homescreen && ./hs.py test        # prints "ok", no phone needed
```

Any folder works in place of `~/iphone-homescreen`. Start a new Claude Code session afterwards so the skill is picked up.

## How to use it

Plug in the phone, unlock it, and ask in plain words. For example:

- "Organise my iPhone apps into folders by what I use them for. Keep page 1 as it is."
- "Show me what you would do before changing anything."
- "Move Slack to page 2." / "Put all my bank apps in one folder called Finance."
- "Back up my Home Screen." / "Undo the last change."
- `/iphone-homescreen` followed by any of the above.

Every use starts with a backup of the phone's layout. Claude then asks how you want the icons reorganised, shows the proposed layout, and sends it only after a yes.

## Where the tool is

The tool is two folders above this skill, and the user's files are in a data folder the tool names:

```
REPO=$(cd -P "${CLAUDE_SKILL_DIR}" && cd ../.. && pwd)
DATA=$("$REPO/hs.py" data)
```

Run every command from `$REPO`. `layout.txt`, `layout.proposed.txt`, `plan.txt`, `RULES.md` and `backups/` are in `$DATA`: the same folder as `$REPO` for a clone, `~/iphone-homescreen-data` for a plugin install (a plugin update replaces the plugin's own folder). Setting `HS_DATA` picks another folder. `$REPO/README.md` describes the `layout.txt` format; read it before editing a layout by hand.

## Before anything

1. The iPhone must be plugged in and unlocked. "Device is password protected" means it is locked: ask the user to unlock it and tap Trust.
2. The phone must not be in jiggle mode (icons wobbling). In jiggle mode the read-back shows an empty extra page in every folder and the check fails. Ask the user to press Done, then read again.

## Every time, in this order

1. **Back up first.** Run `./hs.py backup` before anything else, every time the skill is used, even when the user only asks a question about their layout. Tell the user the backup file's name. If the backup fails, stop: nothing else runs without it.
2. **Read the phone.** `./hs.py pull`, then read `$DATA/layout.txt`.
3. **Ask how to reorganise.** Ask the user how they want the icons reorganised, and do the sorting yourself from their answer. Ask even when `$DATA/RULES.md` exists: offer "the same rules as last time" as the first choice and quote those rules in one or two lines. Ask which pages must stay untouched. Skip the question only when the request already states the exact change ("move Slack to page 2").
4. Write the answer to `$DATA/RULES.md`, replacing what no longer holds. If the user has no preference, use the defaults under "Grouping rules" and say so.
5. If `$DATA/plan.txt` does not exist or does not match this phone, write it from `layout.txt` following `RULES.md`. `$REPO/plan.example.txt` shows the format.

## The loop

1. The backup from "Every time" is already taken; take another with `./hs.py backup` if the user changed anything on the phone since.
2. Change the plan in `$DATA/plan.txt` (see below), then `python3 propose.py`. It writes `$DATA/layout.proposed.txt` and touches nothing on the phone.
3. Show the user what changes: folders, counts, and where the apps they named ended up. Wait for a yes before step 4. A small move they asked for in so many words needs no second yes.
4. `cp "$DATA/layout.proposed.txt" "$DATA/layout.txt" && ./hs.py apply`. It backs up again, sends, and reads the phone back.
5. Report "Applied and verified" or the diff it printed. On a diff, read the phone once more after a few seconds before concluding anything; if it still differs, say what differs and offer `./hs.py restore`.

For a one-off move it is fine to skip `propose.py`: `./hs.py pull`, edit `$DATA/layout.txt`, `./hs.py apply`. Then make the same change in `plan.txt`, or the next rebuild undoes it.

## The plan in plan.txt

`plan.txt` is the single source of truth for the grouping. `propose.py` turns it into `layout.proposed.txt`.

- `@ Keep N` on the first line is the number of pages, after the dock, that are copied from the phone unchanged and are not in the plan. Set it from the user's answer; `@ Keep 0` puts every page in the plan. The dock is always copied unchanged.
- `@ Page N` starts a page.
- `# Folder name` starts a folder. Lines before the first `#` on a page are loose icons.
- Each line under a folder is one folder page, at most 9 apps, separated by `;`.
- An app is written by its display name. When two apps share a name, or a name has odd characters, write `=identifier` (the text after ` | ` in `layout.txt`).

After a run, check three lines of its output:
- `problems` must be `none`.
- `in the plan but not on the phone` lists apps the user has deleted. Remove them from the plan.
- `NOT GROUPED` lists apps on the phone that the plan does not mention, usually newly installed ones. File each into a folder; ask the user only about the ones whose purpose is unclear.

## Grouping rules

The user's own rules live in `$DATA/RULES.md`. They are private to that user and win over everything here. Without them, and when the user states no preference:

- Leave untouched every page the user did not ask to change.
- Group by what the app is used for, with plain folder names. Not too granular; a use with only two apps joins a broader folder.
- An app whose purpose is unknown stays ungrouped until the user says what it is. Do not guess.

## Limits to respect

- Never leave an installed app out of a layout. iOS puts every left-out app back on the last page and also pulls apps that were only in the App Library onto the Home Screen. The tool cannot hide or uninstall an app; the user does that on the phone. If they want apps gone, put them in a "To Delete" folder so they are easy to find.
- A page holds 24 slots, the dock 4, a folder page 9. A small widget takes 4 slots and only sits in columns 1-2 or 3-4, so place it after an even number of full rows; iOS moves it otherwise.
- Widgets can be moved, not created or resized. A widget cannot go inside a folder.
- `./hs.py restore` with no file restores the newest backup, which after an apply is the state just before it.
- `plan.txt`, `layout.txt`, `layout.proposed.txt`, `backups/` and `RULES.md` list the user's installed apps and preferences. In a clone the `.gitignore` keeps them out of git; never push them to a public repository.
