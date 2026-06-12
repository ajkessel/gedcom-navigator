# GEDCOM Navigator

This application provides useful ways to rapidly explore a GEDCOM file exported from genealogy services like Ancestry, MyHeritage, Geni, and Family Tree Maker:

* Find the closest tagged people (e.g. DNA match) to any other person in a family tree
* Show multiple relationship paths between any two people in your tree
* Browse a person's ancestors in a numbered **Pedigree** (Ahnentafel) report, or their full line of **Descendants** with Henry numbering
* Search your tree for variations on names (maiden/married name, alternate names, fuzzy matching, Hebrew/Cyrillic transliteration) and filter on other information like geographical locations or occupation
* Rapidly explore names and connections, even in a very large tree with very distant connections
* Generate custom images of parts of your tree, expanding or collapsing the connections you want to see and saving them to your clipboard or an image file
* Visualize relationships between any two people graphically

**New here?** Click **Walkthrough** below for a guided, interactive tour that highlights each part of the window and shows what it does. You can also start it any time from **Help ▸ Walkthrough**.

## Images

If your GEDCOM file includes profile photographs, this tool will show them if they can be located. If you have images but aren't seeing them, make sure "Show Profile Images" is checked in Preferences, and that the image paths in your GEDCOM file correspond to paths that can be accessed on your computer.

## The problems this solves

Although there are many genealogy websites and desktop tools, they all have shortcomings when you are managing very large trees (thousands or tens of thousands of records).

For example, many genealogists working with autosomal DNA add unfamiliar people to their family tree based on DNA matches and then build out those people's lines, hoping to find the most recent common ancestor between the match and themselves. After accumulating thousands of these speculative additions, you often end up looking at a person in your tree and thinking: *why is this person here? which DNA match did this branch come from?*

Ancestry, Family Tree Maker, and other standard GEDCOM viewers show you a flat list of everyone you've tagged as a DNA match, but none of them will, given an arbitrary person in the tree, walk outward through the relationship graph and tell you the nearest tagged relative. That is one purpose of this tool.

You can also use this tool to find multiple paths between any two people in your tree and also view individual records from your tree. For example, if your grandfather's maternal cousin married your grandfather's paternal cousin, you will have multiple paths to their descendants. Most applications only show one path--the most direct; this tool can find as many paths as you like. If you set the application to cast a wide net by setting the "max depth" to a high value, you can discover unexpected links between your relatives. This will take longer to process in a large tree but can yield interesting information.

Any relationship description can be clicked to see a graphical representation of that relationship, which you can then copy and use as you like.

Family graphs use line style to show non-biological relationships when the GEDCOM data identifies them. Ordinary biological/default family links, including full-sibling links, are solid. Step-family links use a dash-dot line, adopted or foster links use a dotted or short-dashed line, and half-sibling links use a split sibling connector. The graph includes a compact legend whenever one of these non-ordinary relationship styles is visible, and that legend includes the biological/default line style for comparison.

If you set a person as the "Home Person" using the "Set Home" button, the Display Pane will include the path from the selected person to the Home Person in Profile, Matches, and Paths mode. When the Home Person is selected in the list, the button changes to "Unset Home"; clicking it clears the Home Person.

Finally, if you have a large tree, you may find it difficult to search for specific individuals in other tools. Ancestry, for example, only searches on the person's "preferred name" and not any of the alternate names, and neither Ancestry nor Family Tree Maker allow fuzzy matching searches. Ancestry also does not allow you to easily search on multiple fields simultaneously, like name, location, and occupation. With this tool, you can search for a name with fuzzy matching (e.g. "John Smith" in the "Find:" box) and then further limit the results by a term that appears anywhere in the person's record (e.g. "Chicago" and "tailor" in the "Filter" box). If you have multiple names in a person's record (e.g. maiden name, married name, nicknames), this tool will match any of them. This search method avoids the clumsy workarounds people use to label people in their tree, for example, by packing all the person's different surnames into the surname field. You can create a separate "name" record for each name the person has, and then find them easily using this tool's search functionality.

I've also sought to make all actions accessible from the keyboard. See [the keyboard shortcuts list](KEYBOARD_SHORTCUTS.md) for guidance. This makes it very fast to search for and compare people, even in a very large tree.

## How it works

Given a GEDCOM file and a target individual, the tool performs a breadth-first search through the tree's relationship graph (parents, children, siblings, spouses) and returns the closest individuals flagged as DNA matches, along with the relationship path connecting each match to the target.

For parent-child relationships, the tool reads GEDCOM pedigree metadata such as `FAMC`/`PEDI`, adoption records, and common Family Tree Maker relationship tags like `_FREL` and `_MREL`. If a GEDCOM file does not say otherwise, a parent-child link is treated as an ordinary biological/default relationship, which matches common GEDCOM export practice.

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

**Files not exported by Ancestry** do not contain `_MTTAG` records. For those, the tool automatically looks for the custom fields other genealogy programs (RootsMagic, Gramps, Family Historian, Legacy, etc.) use to record DNA matches — custom events and facts (`EVEN`/`FACT` with a `TYPE` such as "DNA Match"), custom attributes (`_ATTR`), reference numbers (`REFN`), and custom `_DNA`-style tags — matching the same tag keyword. Free-text notes are not scanned by default. Use the **Select Tag** button to see which custom field types were found in your file and choose one to match on.

Although this software was developed for this DNA use case, you could use it to find the closest path to any tag or page marker by entering that string into "tag keyword" or "page marker" rather than a DNA-specific term. For example, if your paternal relatives are tagged with a "paternal" tag, you could use this tool to find the path between anyone in your tree and anyone tagged as a paternal relative.

## Profile View: Bio, Pedigree, and Descendants

When a person is selected, the **Profile** pane offers three sub-views via the **Bio / Pedigree / Descendants** selector (or keyboard shortcuts **Ctrl+B**, **Ctrl+Shift+P**, **Ctrl+Shift+D** — use **⌘** in place of **Ctrl** on macOS):

### Bio

The biographical profile for the selected person: vital dates, family members, facts and events, path to the Home Person, and the optional full GEDCOM record.

### Pedigree

An **Ahnentafel** ("ancestor table") report. Every ancestor is assigned a unique number that encodes exactly where they sit in the family tree:

| Slot | Relationship |
| --- | --- |
| 1 | The selected person |
| 2 | Father |
| 3 | Mother |
| 4 | Paternal grandfather |
| 5 | Paternal grandmother |
| 6 | Maternal grandfather |
| 7 | Maternal grandmother |
| 8–15 | Great-grandparents |
| 16–31 | 2nd great-grandparents |

**The rule:** for any person at slot *n*, their father is at slot **2n** and their mother is at slot **2n + 1**. To trace any ancestor back to the selected person, halve the slot number (discarding any remainder) and repeat until you reach 1.

**Example:** slot 13 → 6 (maternal grandfather) → 3 (mother) → 1 (you). So slot 13 is the mother's maternal grandfather.

Ancestors appear grouped by generation. Great-grandparents and beyond use compact ordinal labels ("2nd great-grandfather", "3rd great-grandfather") rather than repeating "great-". Each entry also carries a paternal or maternal prefix showing which side of the family the ancestor belongs to. Only ancestors actually present in the GEDCOM file are listed — unknown ancestors are skipped rather than shown as placeholders.

### Descendants

A **Henry-numbered** descendant report. The selected person is **1**; their children are **1.1**, **1.2**, …; grandchildren are **1.1.1**, **1.1.2**, …, and so on. Each person's spouse is listed just below them.

### Navigating and saving

Person names in Pedigree and Descendants are clickable links that navigate to that person's Bio. Both reports are plain text, so **Copy** (Ctrl+C / ⌘C) and **Save** (Ctrl+S / ⌘S) work the same way as for any other result view.
