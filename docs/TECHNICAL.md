## How the DNA matching works

![Main
window](https://raw.githubusercontent.com/ajkessel/gedcom-navigator/main/docs/screenshots/main-window.png)

Given a GEDCOM file and a target individual, the tool performs a breadth-first search through the tree's relationship graph (parents, children, siblings, spouses) and returns the closest individuals flagged as DNA matches, along with the relationship path connecting each match to the target.

Two flag formats are recognized by default:

- **AncestryDNA citations.** When an Ancestry-managed tree marks a person as a DNA match, the exported GEDCOM contains a source citation with a `PAGE` line of the form:
  ```
  2 PAGE AncestryDNA Match to Jane Q. Doe
  ```
- **MyTreeTags / Family Tree Maker custom tags.** Tags applied via Ancestry MyTreeTags or as a custom fact in Family Tree Maker show up as a pointer to a tag-definition record:
  ```
  1 _MTTAG @T182059@
  ```
  with the corresponding definition elsewhere in the file:
  ```
  0 @T182059@ _MTTAG
  1 NAME DNA Match
  ```

Both substrings are configurable, so you can adapt the tool to other genealogy software's conventions.

Although this software was developed for this DNA use case, you could use it to find the closest path to any tag or page marker by entering that string into "tag keyword" or "page marker" rather than a DNA-specific term. For example, if your paternal relatives are tagged with a "paternal" tag, you could use this tool to find the path between anyone in your tree and anyone tagged as a paternal relative.

## Requirements

The pre-built executables have no requirements.

If you want to run these scripts from the source code, you will need:

- Python 3.8 or newer
- [customtkinter](https://github.com/tomschimansky/customtkinter) (GUI only)
- [CTKToolTip](https://github.com/Akascape/CTkToolTip) (GUI only)
- [cyrtranslit](https://pypi.org/project/cyrtranslit/) (packaged/source builds; enhanced Cyrillic name transliteration)
- [hebrew](https://pypi.org/project/hebrew/) (packaged/source builds; Hebrew text normalization before built-in transliteration)
- [Pillow](https://python-pillow.org/) (GUI graph image export/clipboard support)
- [PyObjC Cocoa](https://pyobjc.readthedocs.io/) (macOS GUI graph clipboard support)

The command-line interface does not require third-party packages. If `cyrtranslit` or `hebrew` is installed, the parser uses them to improve cached transliterated-name aliases; otherwise it falls back to built-in Hebrew and Cyrillic mappings.

## Installation

### Pre-built executables

Download the [latest release for your operating system](https://github.com/ajkessel/gedcom-navigator/releases/latest). No Python installation required.

### pip (PyPI)

This application is also available on [PyPI via pip](https://pypi.org/project/gedcom-navigator/). For the command-line interface only, use:
```
pip install gedcom-navigator
```

For the graphical interface, install the GUI extra:

```
pip install "gedcom-navigator[gui]"
```

After installation two commands are available:

| Command                | Description            |
| ---------------------- | ---------------------- |
| `gedcom-navigator`     | Command-line interface |
| `gedcom_navigator_gui` | Graphical interface    |

On Linux, install your distribution's tkinter package before using the GUI:

```
# install python-tk
# Debian / Ubuntu
sudo apt install python3-tk

# Fedora
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk
```

For Linux-specific GUI troubleshooting notes, including WSL/X server checks and
CustomTkinter font warnings, see [Linux Issues](LINUX_ISSUES.md).

### Run from source

```
git clone https://github.com/ajkessel/gedcom-navigator.git
cd gedcom-navigator
python -m venv .venv
source .venv/bin/activate
pip install -r dev/requirements.txt
python src/gedcom_navigator_gui.py        # GUI
python src/gedcom_navigator_cli.py --help # CLI
```

The CLI can run without these GUI dependencies. If you want to build distributable packages, swap `requirements-dev.txt` for `requirements.txt` above.

### Build executables yourself

Use [build.sh](../dev/build.sh) to compile for Linux or Mac and [build.ps1](../dev/build.ps1) for Windows. The build script automatically creates a Python virtual environment and installs the required dependencies.

A [build-and-release.sh](../dev/build-and-release.sh) script is also available that builds for all three platforms under WSL.

## Usage

For pre-built binaries, just run the executable, or download directly from the [Mac App Store](https://apps.apple.com/app/gedcom-navigator/id6765485580). 

### Relationship finder

This is an alternate use of this tool. Select a person in the search panel, switch the Display Pane to **Paths**, and select a second person when prompted. The Display Pane will then show the top three paths (if they exist) between those two people. You can change the number of paths to an arbitrary number by editing the "Top N" value in the bottom right. If the two people are very distantly related, you may need to increase the "Max Depth" setting to find the connection. The default max depth of 50 should find connections at least up to 4th cousins.

![Relationship
window](https://raw.githubusercontent.com/ajkessel/gedcom-navigator/main/docs/screenshots/relationship-path.png)


### GUI

```
python gedcom_navigator_gui.py                  # opens with no file loaded
python gedcom_navigator_gui.py /path/to/tree.ged   # auto-loads on startup
```

1. Click **Browse** and select your `.ged` file (or pass it on the command line as shown above). The tool will also find a `.ged` file inside a `.zip` file, since a tree downloaded from Ancestry will be zipped.
2. Optionally adjust the tag keyword (default `DNA`) or page marker (default `AncestryDNA Match`). The defaults work for files exported from Ancestry and Family Tree Maker.
3. Click **Load**. The status bar will show how many individuals, families, and DNA-flagged people were found.
4. Type a name or INDI ID into the search box to filter the people list. Names are matched by whitespace-separated tokens, in any order, each as a case-insensitive substring — so `John Smith` will find `John Adam Smith`. When fuzzy matching is enabled, cached English-letter aliases for Hebrew and Cyrillic names are also searched. The aliases are generated locally when the GEDCOM is parsed, stored in the parsed-data cache, and are approximate; the original GEDCOM names are not modified. The "DNA-flagged only" checkbox hides everyone else.
5. Select a person and switch the Display Pane to **Matches**.
6. The Display Pane shows the closest flagged relative(s) and the relationship path from the selected person to each one.

![Results pane showing a relationship
path](https://raw.githubusercontent.com/ajkessel/gedcom-navigator/main/docs/screenshots/results-pane.png)

The **View tag definitions...** button opens a window listing every `_MTTAG` record in the file with its name, which is useful for deciding what tag-keyword filter to use.

### Command line

```
# List all _MTTAG definitions in the file (use "_" as a placeholder for the target)
python gedcom_navigator_cli.py tree.ged --list-tags _

# List every flagged individual
python gedcom_navigator_cli.py tree.ged --list-flagged _

# Find the three nearest DNA-flagged relatives by name
python gedcom_navigator_cli.py tree.ged "Jane Doe"

# Names are matched by whitespace-separated tokens, in any order, each as
# a case-insensitive substring. The middle name is not required:
# this matches "John Adam Smith".
python gedcom_navigator_cli.py tree.ged "John Smith"

# Fuzzy matching tolerates typos and spelling variants. The default
# similarity threshold is 0.6; raise it for stricter matches.
python gedcom_navigator_cli.py tree.ged "John Smth" --fuzzy
python gedcom_navigator_cli.py tree.ged "John Smth" --fuzzy --fuzzy-threshold 0.75

# Find by exact INDI ID
python gedcom_navigator_cli.py tree.ged @I1234@

# Restrict the tag filter to actual DNA matches only (excludes
# "DNA Connection" or "Common DNA Ancestor" if you use those tags)
python gedcom_navigator_cli.py tree.ged "Jane Doe" --tag-keyword "DNA Match"

# Return the top 5 nearest matches with a deeper search
python gedcom_navigator_cli.py tree.ged "Jane Doe" --top 5 --max-depth 80
```

#### Full CLI options

| Flag                | Default             | Description                                                                 |
| ------------------- | ------------------- | --------------------------------------------------------------------------- |
| `--top`             | 3                   | Number of nearest matches to return.                                        |
| `--max-depth`       | 50                  | Maximum BFS depth, in edges.                                                |
| `--page-marker`     | `AncestryDNA Match` | Substring to look for in source-citation `PAGE` text. Case-insensitive.     |
| `--tag-keyword`     | `DNA`               | Substring to look for in `_MTTAG` `NAME` values. Case-insensitive.          |
| `--fuzzy`           | off                 | Enable fuzzy name matching for typos and spelling variants.                 |
| `--fuzzy-threshold` | 0.6                 | Similarity cutoff for `--fuzzy`, between 0.0 and 1.0. Lower = more matches. |
| `--list-tags`       |                     | Print all `_MTTAG` definitions in the file and exit.                        |
| `--list-flagged`    |                     | Print every individual currently flagged as a DNA match and exit.           |

## Example output

```
Starting from: John A. Smith (1850-1920) [@I1234@]

#1: Mary E. Doe (1965-) [@I9876@]    (distance: 5 edges)
   DNA markers:
     - Source citation PAGE: "AncestryDNA Match to Mary E. Doe"
   Path:
     John A. Smith (1850-1920) [@I1234@]
       --[child]--> Robert Smith (1880-1950) [@I1240@]
       --[child]--> Helen Smith (1910-1985) [@I1245@]
       --[child]--> Janet Smith (1942-) [@I1250@]
       --[child]--> Mary E. Doe (1965-) [@I9876@]
```

## Caveat for Ancestry users

Ancestry's GEDCOM export is well known to be lossy and its handling of MyTreeTags has varied across versions. If this tool reports far fewer flagged individuals than you expected, load the file and click **View tag definitions...** (or run `--list-tags _` from the command line) to confirm whether your tag records actually made it into the export. If they did not, the workarounds are:

1. Sync the Ancestry tree to Family Tree Maker, add a custom fact (for example, named `DNA Match`) on those individuals in FTM, then export the GEDCOM from FTM. Custom facts in FTM survive the GEDCOM export reliably.
2. Or rely on the `2 PAGE AncestryDNA Match to ...` citation, which *is* generated automatically by Ancestry when you tag a person as a DNA match while building their tree from a match's profile.

Run the tool with `--list-flagged _` (CLI) or use the "DNA-flagged only" checkbox (GUI) right after loading to confirm the flagged set looks complete before drawing conclusions from any individual query.

## How "closest" is defined

The tool measures distance as the number of edges traversed in the GEDCOM relationship graph. Each of the following counts as one edge:

- parent ↔ child
- sibling ↔ sibling (within the same `FAM` record)
- spouse ↔ spouse

This means a sibling and a parent are treated as equidistant from ego (both are one edge away), which fits the practical question "how many hops do I need to figure out why this person is in my tree" but is not the same as a genealogical relationship coefficient.

## Limitations and notes

- Edge weighting is uniform, as described above. If you would prefer to weight blood relationships and marriages differently, the `neighbors()` function is the place to change it. I might make this a configurable setting at some point in the future.
- The BFS stops as soon as it has accumulated `--top` matches at shortest distances. It does not guarantee a globally optimal cover of *all* equally close matches if there is a tie at the boundary — raise `--top` if you suspect ties.
- Custom tags whose names happen to contain the substring `DNA` will also be picked up under the default `--tag-keyword`. Use a more specific keyword, such as `"DNA Match"`, if you want to exclude Ancestry's `DNA Connection` and `Common DNA Ancestor` tags.
- The tool does not write back to your GEDCOM and does not phone home; it reads the file and prints results.
- Tested with GEDCOM 5.5.1 files exported from Ancestry and Family Tree Maker. Files from other software should work as long as they use standard `INDI` / `FAM` / `HUSB` / `WIFE` / `CHIL` structures and one of the two recognized flag formats (or a substitute that you configure via `--tag-keyword` and `--page-marker`).

## Privacy

The tool runs entirely locally on your machine. Nothing is uploaded. Be aware, however, that your `.ged` file likely contains personal information about living people; do not commit your real GEDCOM to a public repository or create issues or provide feedback to this repository with any personal data.
