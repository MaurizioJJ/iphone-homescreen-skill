# iphone-homescreen

Rearrange an iPhone Home Screen from a Mac: pull the layout into a text file, edit it, apply it back over a USB cable. No jailbreak and nothing to install on the phone.

It comes with a [Claude Code](https://claude.com/claude-code) skill, so you can say "organise my iPhone apps by what I use them for" and let Claude do the sorting.

Tested on one phone only: an iPhone 16 on iOS 27.2. Every apply takes a backup first, and `./hs.py restore` puts it back.

## Install

Needs a Mac with [`uv`](https://docs.astral.sh/uv/) (`brew install uv`).

As a Claude Code plugin:

```
/plugin install iphone-homescreen --marketplace MaurizioJJ/iphone-homescreen-skill
```

On an older Claude Code, in two steps from the terminal:

```
claude plugin marketplace add MaurizioJJ/iphone-homescreen-skill
claude plugin install iphone-homescreen@iphone-homescreen-skill
```

Or clone it, to use the scripts by hand as well:

```
git clone https://github.com/MaurizioJJ/iphone-homescreen-skill ~/iphone-homescreen
cd ~/iphone-homescreen && ./hs.py test        # prints "ok", no phone needed
ln -s ~/iphone-homescreen/skills/iphone-homescreen ~/.claude/skills/iphone-homescreen
```

Start a new Claude Code session afterwards.

## Use with Claude

Plug the iPhone in with a data cable, unlock it, tap Trust, then ask:

- "Organise my iPhone apps into folders by what I use them for. Keep page 1 as it is."
- "Move Slack to page 2."
- "Undo the last change."

Claude backs up the layout, asks how you want the icons reorganised, shows you the proposed layout, and sends it only after you say yes.

## Use by hand

```
./hs.py pull              # phone -> layout.txt
./hs.py apply             # layout.txt -> phone
./hs.py backup            # phone -> backups/
./hs.py restore           # newest backup -> phone
./hs.py restore FILE      # a specific backup -> phone
./hs.py data              # print the folder your files are in
./hs.py test              # self-check, no phone needed
```

`apply` saves the phone's current layout to `backups/` before it writes, then reads the phone back and confirms it matches.

### layout.txt

```
== Dock
Safari | com.apple.mobilesafari

== Page 1
Photos | com.apple.mobileslideshow
[widget small] com.apple.weather | 00000000-0000-0000-0000-000000000000
Folder: Travel
    Maps | com.apple.Maps
    --
    Compass | com.apple.compass
```

- One item per line. Only the identifier after the last ` | ` matters; the name before it is for reading.
- `== ` starts a page. The first one is the dock.
- `Folder: Name` starts a folder; its items are indented. `--` (indented) starts the folder's next page.
- Move lines to move items. Add a `Folder:` line to make a folder, a `==` line to make a page.
- Lines starting with `#` are ignored.

`apply` refuses, and sends nothing, when the file lists an item twice, names one that is not on the phone, overfills a page (24 slots; a small widget takes 4, medium 8, large 16), the dock (4) or a folder page (9), or leaves out an item that is on the phone.

### plan.txt

For a full regrouping, a plan is easier than moving hundreds of lines. `plan.txt` lists pages, folders and the apps in each; `plan.example.txt` shows the format.

- `@ Page N` starts a page; `# Name` starts a folder. Lines before the first `#` on a page are loose icons.
- Each line under a folder is one folder page: up to 9 apps, separated by `;`.
- Write an app by its name as shown in `layout.txt`, or as `=identifier` when two apps share a name.
- The example uses made-up names. Replace every one with apps from your own phone, or `propose.py` refuses the plan.

```
cp plan.example.txt plan.txt          # then fill it in
./hs.py backup                        # so the plan sees the phone as it is now
python3 propose.py                    # writes layout.proposed.txt, phone untouched
cp layout.proposed.txt layout.txt     # accept it
./hs.py apply                         # send it to the phone
```

`@ Keep N` sets how many pages after the dock are copied from the phone unchanged. Apps on the phone that the plan does not mention land on pages called "Not grouped" at the end; apps in the plan that are no longer on the phone are skipped.

## Limits

- It cannot remove or uninstall an app. iOS puts every left-out app back on the last page, and brings apps that were only in the App Library out with them. Delete or hide apps on the phone itself.
- Widgets can be moved but not created or resized. A small widget only sits in columns 1-2 or 3-4; iOS moves it otherwise.
- Do not apply while the phone is in jiggle mode: the read-back then shows an empty extra page in every folder.
- The limits are the iPhone grid (6 rows of 4). An iPad needs different numbers at the top of `hs.py`.

## Your data

`plan.txt`, `layout.txt`, `layout.proposed.txt`, `backups/` and `RULES.md` list your installed apps and stay on your Mac. In a clone they sit next to `hs.py` and `.gitignore` keeps them out of git. Installed as a plugin they are in `~/iphone-homescreen-data`, because a plugin update replaces the plugin's own folder. Set `HS_DATA` to use another folder. Nothing is sent anywhere except to your own phone over the cable.
