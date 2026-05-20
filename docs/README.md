# GEDCOM Navigator

## Who is this for?

This application is for genealogists who manage large GEDCOM files, particularly with tags for DNA matches.

## What does it do?

This application provides useful ways to rapidly explore a GEDCOM file exported from genealogy services like Ancestry, MyHeritage, Geni, and Family Tree Maker:

* Find the closest tagged people (e.g. DNA match) to any other person in a family tree
* Show multiple relationship paths between any two people in your tree
* Search your tree for variations on names (maiden/married name, alternate names, fuzzy matching) and filter on other information like geographical locations or occupation
* Rapidly explore names and connections, even in a very large tree with very distant connections
* Generate custom images of parts of your tree, expanding or collapsing the connections you want to see and saving them to your clipboard or an image file
* Visualize relationships between any two people graphically

The tool does not modify your GEDCOM file. It is only used for exploring connections.

In addition to the GUI, this application also includes a command-line tool for fast queries or incorporating into other programmatic workflows.

Downloads:
* Mac
** [App Store](https://apps.apple.com/app/gedcom-navigator/id6765485580) - easy install, may be behind the latest version here
** [ZIP Download](https://github.com/ajkessel/gedcom-navigator/releases/latest/download/gedcom-navigator-mac.zip) (see [security note](#macos-security))
* Windows
** App Store (coming soon)
** [Portable Version](https://github.com/ajkessel/gedcom-navigator/releases/latest/download/gedcom-navigator-windows-portable.zip) (see [security note](#windows-security))
** [Installer](https://github.com/ajkessel/gedcom-navigator/releases/latest/download/gedcom-navigator-windows-installer.exe)
* [Linux](https://github.com/ajkessel/gedcom-navigator/releases/latest/download/gedcom-navigator-linux.zip)

![Main
window](https://raw.githubusercontent.com/ajkessel/gedcom-navigator/main/docs/screenshots/screen_recording.gif)

This is an alpha release. Only one person has tested it so far--me. If you are interested in experimenting with a "dummy" GEDCOM file rather than your own, several are available from [the FindMyPast Github Repository](https://github.com/findmypast/gedcom-samples). I used the [Game of Thrones family tree](https://github.com/findmypast/gedcom-samples/blob/main/GoT.ged) for the sample screenshots to avoid any privacy issues and also to show why it gets complicated when siblings marry one another.

## The problems this solves

Many genealogists working with autosomal DNA add unfamiliar people to their family tree based on DNA matches and then build out those people's lines, hoping to find the most recent common ancestor between the match and themselves. After accumulating thousands of these speculative additions, you often end up looking at a person in your tree and thinking: *why is this person here? which DNA match did this branch come from?*

Ancestry, Family Tree Maker, and other standard GEDCOM viewers show you a flat list of everyone you've tagged as a DNA match, but none of them will, given an arbitrary person in the tree, walk outward through the relationship graph and tell you the nearest tagged relative. That is the main purpose of this tool.

You can also use this tool to find multiple paths between any two people in your tree and also view individual records from your tree. For example, if your grandfather's maternal cousin married your grandfather's paternal cousin, you will have multiple paths to their descendants. Most applications only show one path; this tool can find as many paths as you like. If you set the application to cast a wide net by setting the "max depth" to a high value, you can discover unexpected links between your relatives. This will take longer to process in a large tree but can yield interesting information.

Any relationship description can be clicked to see a graphical representation of that relationship, which you can then copy and use as you like.

If you set a person as the "Home Person" using the "Set Home" button, the results will always include the path from the selected person to the Home Person in addition to the closest people with DNA match markers.

Finally, if you have a large tree, you may find it difficult to search for specific individuals in other tools. Ancestry, for example, only searches on the person's "preferred name" and not any of the alternate names, and neither Ancestry nor Family Tree Maker allow fuzzy matching searches. Ancestry also does not allow you to easily search on multiple fields simultaneously, like name, location, and occupation. With this tool, you can search for a name with fuzzy matching (e.g. "John Smith" in the "Find:" box) and then further limit the results by a term that appears anywhere in the person's record (e.g. "Chicago" and "tailor" in the "Filter" box). If you have multiple names in a person's record (e.g. maiden name, married name, nicknames), this tool will match any of them. This search method avoids the clumsy workarounds people use to label people in their tree, for example, by packing all the person's different surnames into the surname field. You can create a separate "name" record for each name the person has, and then find them easily using this tool's search functionality.

I've also sought to make all actions accessible from the keyboard. See [the keyboard shortcuts list](KEYBOARD_SHORTCUTS.md) for guidance. This makes it very fast to search for and compare people, even in a very large tree.

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
- [Pillow](https://python-pillow.org/) (GUI graph image export/clipboard support)
- [PyObjC Cocoa](https://pyobjc.readthedocs.io/) (macOS GUI graph clipboard support)

The command-line interface uses only the Python standard library.

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

| Command                 | Description            |
| ----------------------- | ---------------------- |
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

This is an alternate use of this tool. Select a person in the search panel, then click on "Find Relationship Path..." and select a second person. This tool will then show you the top three paths (if they exist) between those two people. You can change the number of paths to an arbitrary number by editing the "Top N" value in the bottom right. If the two people are very distantly related, you may need to increase the "Max Depth" setting to find the connection. The default max depth of 50 should find connections at least up to 4th cousins.

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
4. Type a name or INDI ID into the search box to filter the people list. Names are matched by whitespace-separated tokens, in any order, each as a case-insensitive substring — so `John Smith` will find `John Adam Smith`. The "DNA-flagged only" checkbox hides everyone else.
5. Select a person and click **Find Nearest DNA Matches** (or just double-click the row).
6. The right pane shows the closest flagged relative(s) and the relationship path from the selected person to each one.

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

## Windows security

You may get a warning from Windows Defender that this is an unrecognized app from an unknown publisher. You can run the application by clicking first on "more info" and then "run anyway." It should only ask the first time you execute the software.

![Windows
Screenshot](https://raw.githubusercontent.com/ajkessel/gedcom-navigator/main/docs/screenshots/windows-security.png)

## MacOS security

If you install from the [Mac App Store](https://apps.apple.com/app/gedcom-navigator/id6765485580), this application should just work out of the box. If you are downloading the application from here and not running from the source code, you will have to tell the operating system manually to trust the program. As of 29 April 2026, I am testing a new build process that should only require one click to approve after downloading--just select "open" when presented with the box below the first time you run a new version of the application.

![Mac
Screenshot](https://raw.githubusercontent.com/ajkessel/gedcom-navigator/main/docs/screenshots/downloaded-from-internet.png)

## License

This project is released under the BSD 2-Clause License. See the [`LICENSE`](LICENSE.md) file for the full text.

## Recent changes

See [`CHANGELOG`](CHANGELOG.md).

## Contributing

Bug reports, feature suggestions, and pull requests are welcome. If you encounter a GEDCOM file whose tag format is not recognized, please open an issue and include the relevant excerpt (with personal names redacted) so the parser can be extended.
