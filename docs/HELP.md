# GEDCOM Navigator

This tool provides useful ways to rapidly explore a GEDCOM file exported from genealogy services like Ancestry, MyHeritage, Geni, and Family Tree Maker:

* Find the closest tagged people (e.g. DNA match) to any other person in a family tree
* Show multiple relationship paths between any two people in your tree
* Search your tree for variations on names (maiden/married name, alternate names, fuzzy matching) and filter on other information like geographical locations or occupation
* Rapidly explore names and connections, even in a very large tree with very distant connections
* Generate custom images of parts of your tree, expanding or collapsing the connections you want to see
* Visualize relationships between any two people graphically

## The problems this solves

Although there are many genealogy websites and desktop tools, they all have shortcomings when you are managing very large trees (thousands or tens of thousands of records).

For example, many genealogists working with autosomal DNA add unfamiliar people to their family tree based on DNA matches and then build out those people's lines, hoping to find the most recent common ancestor between the match and themselves. After accumulating thousands of these speculative additions, you often end up looking at a person in your tree and thinking: *why is this person here? which DNA match did this branch come from?*

Ancestry, Family Tree Maker, and other standard GEDCOM viewers show you a flat list of everyone you've tagged as a DNA match, but none of them will, given an arbitrary person in the tree, walk outward through the relationship graph and tell you the nearest tagged relative. That is one purpose of this tool.

You can also use this tool to find multiple paths between any two people in your tree and also view individual records from your tree. For example, if your grandfather's maternal cousin married your grandfather's paternal cousin, you will have multiple paths to their descendants. Most applications only show one path--the most direct; this tool can find as many paths as you like. If you set the application to cast a wide net by setting the "max depth" to a high value, you can discover unexpected links between your relatives. This will take longer to process in a large tree but can yield interesting information.

Any relationship description can be clicked to see a graphical representation of that relationship, which you can then copy and use as you like.

If you set a person as the "Home Person" using the "Set Home" button, the results will always include the path from the selected person to the Home Person in addition to the closest people with DNA match markers.

Finally, if you have a large tree, you may find it difficult to search for specific individuals in other tools. Ancestry, for example, only searches on the person's "preferred name" and not any of the alternate names, and neither Ancestry nor Family Tree Maker allow fuzzy matching searches. Ancestry also does not allow you to easily search on multiple fields simultaneously, like name, location, and occupation. With this tool, you can search for a name with fuzzy matching (e.g. "John Smith" in the "Find:" box) and then further limit the results by a term that appears anywhere in the person's record (e.g. "Chicago" and "tailor" in the "Filter" box). If you have multiple names in a person's record (e.g. maiden name, married name, nicknames), this tool will match any of them. This search method avoids the clumsy workarounds people use to label people in their tree, for example, by packing all the person's different surnames into the surname field. You can create a separate "name" record for each name the person has, and then find them easily using this tool's search functionality.

I've also sought to make all actions accessible from the keyboard. See [the keyboard shortcuts list](KEYBOARD_SHORTCUTS.md) for guidance. This makes it very fast to search for and compare people, even in a very large tree.

## How it works

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