"""
gedcom_strings.py

Standardized string definitions using gettext for localization.
To access strings, import this module and use the constants.
"""

import sys
from gedcom_i18n import _
from gedcom_shortcuts import keyboard_shortcut_rows as _shortcut_rows, shortcut_by_action as _shortcut_by_action

# Helper for dynamic key labels
def get_mod_key():
    return '⌘' if sys.platform == 'darwin' else 'Ctrl+'

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
APP_TITLE = _("GEDCOM Navigator")
STATUS_NO_FILE = _("No file loaded.")

# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
MENU_FILE = _("File")
MENU_OPEN_GEDCOM = _("Open GEDCOM File…")
MENU_OPEN_RECENT = _("Open Recent")
MENU_NO_RECENT_FILES = _("No Recent Files")
MENU_MENU = _("Help")
MENU_PREFERENCES = _("Settings…") if sys.platform == 'darwin' else _("Preferences… (F3)")

def get_menu_how_to_use():
    mod = get_mod_key()
    return (
        _("How to use ({mod}?)").format(mod=mod)
        if sys.platform == 'darwin'
        else _("How to use (F1)")
    )

def get_menu_keyboard_shortcuts():
    mod = get_mod_key()
    return (
        _("Keyboard shortcuts ({mod}K)").format(mod=mod)
        if sys.platform == 'darwin'
        else _("Keyboard Shortcuts (F2)")
    )

def get_menu_walkthrough():
    return _("Walkthrough")

MENU_CHECK_FOR_UPDATES = _("Check for updates…")
MENU_PRIVACY_POLICY = _("Privacy Policy")
MENU_ABOUT = _("About")
MENU_QUIT = _("Quit")

# ---------------------------------------------------------------------------
# File panel
# ---------------------------------------------------------------------------
DLG_SELECT_GEDCOM = _("Select GEDCOM file")

# ---------------------------------------------------------------------------
# DNA marker settings panel
# ---------------------------------------------------------------------------
LBL_TAG_KEYWORD = _("Tag keyword:")
LBL_PAGE_MARKER = _("Page marker:")
BTN_SELECT_TAG = _("Select Tag")

# ---------------------------------------------------------------------------
# People list
# ---------------------------------------------------------------------------
LBL_FIND = _("Find:")
CHK_DNA_FLAGGED_ONLY = _("Tagged")
CHK_FUZZY = _("Fuzzy")
CHK_MARRIED_NAMES = _("Married")
LBL_FILTER = _("Filter:")
COL_NAME = _("Name")
COL_BIRTH = _("Birth")
COL_DEATH = _("Death")
COL_DNA = _("Tagged")

# ---------------------------------------------------------------------------
# Action controls (main window)
# ---------------------------------------------------------------------------
LBL_TOP_N = _("Results:")
LBL_MAX_DEPTH = _("Max Depth:")
BTN_SHOW_PERSON = _("Profile")
BTN_SHOW_PERSON_TREE = _("Tree")
BTN_SET_HOME = _("Set Home")

# ---------------------------------------------------------------------------
# Display Pane
# ---------------------------------------------------------------------------
DISPLAY_MODE_PROFILE = _("Profile")
DISPLAY_MODE_MATCHES = _("Matches")
DISPLAY_MODE_PATHS = _("Paths")
BTN_FIND_MATCHES = DISPLAY_MODE_MATCHES
BTN_COPY = _("Copy")
BTN_REVERSE = _("Reverse")
BTN_REVERSE_RESTORE = _("Normal Path")
BTN_SAVE = _("Save")

def get_tip_reverse():
    mod = get_mod_key()
    return (
        _("Reverse ({mod}R)\n"
          "Reverse the direction of all relationship paths shown, computing "
          "the relationship from the other person's perspective. "
          "Click again to restore the original path.").format(mod=mod)
    )

# ---------------------------------------------------------------------------
# Tooltips
# ---------------------------------------------------------------------------
def get_tip_copy():
    mod = get_mod_key()
    return (
        _("Copy results ({mod}C)\n"
          "Copy the entire contents of the results pane to the clipboard. "
          "When the results text area has keyboard focus, "
          "{mod}C copies only the selected text as usual.").format(mod=mod)
    )

def get_tip_copy_json():
    mod = get_mod_key()
    return (
        _("Copy JSON ({mod}J)\n"
          "Copy the entire contents of the results pane as JSON to the clipboard. "
          "Used only for debugging.").format(mod=mod)
    )

def get_tip_save():
    mod = get_mod_key()
    return _("Save ({mod}S)\nSave the results to a text file.").format(mod=mod)

def get_tip_find():
    mod = get_mod_key()
    return (
        _("Find ({mod}F)\n"
          "Type to filter the list of people. Search by any name variation. Use the filter box "
          "to search by other information in a person's GEDCOM record, such as geographic location. "
          "Press Enter to jump directly to the first match. "
          "Use the checkboxes to show only people matching tags, allow fuzzy name matching "
          "(including Cyrillic and Hebrew characters), or include married names.").format(mod=mod)
    )

def get_tip_find_matches():
    mod = get_mod_key()
    return (
        _("Matches ({mod}N)\n"
          "Show the closest tagged matches to the selected person. "
          "The results are ranked by proximity to the selected person, with ties broken by "
          "the number of tags (if any) associated with the match. "
          "Use the 'Results' and 'Max Depth' settings to adjust how many results are returned and "
          "how far to search within the tree.").format(mod=mod)
    )

def get_tip_filter():
    mod = get_mod_key()
    return (
        _("Filter ({mod}I)\n"
          "Type to filter the list of people by any information in their GEDCOM record, "
          "such as geographic location. This filter is applied in addition to the Find box above.").format(mod=mod)
    )

TIP_TAG_KEYWORD = _(
    "Enter a keyword to filter the list of tags used for finding relationship paths. "
    "Leave this blank to use only the page marker keyword to find relationship paths."
)
TIP_PAGE_MARKER = _(
    "Enter a unique keyword to use as a page marker when finding relationship paths. "
    "Leave this blank to use only the tag keyword to find relationship paths."
)

def get_tip_set_home():
    display = _shortcut_by_action('set_home').display
    return _("Set Home Person ({display})\nSet the selected person as the home person for finding relationship paths.").format(display=display)

def get_tip_show_person():
    return _("Profile\nShow the selected person's biographical, family, tag, and optional full GEDCOM record details in the Display Pane.")

def get_tip_show_person_tree():
    mod = get_mod_key()
    return _("Tree View ({mod}E)\nOpen the configured default tree view for the selected person. Shift-Click for Profile View.").format(mod=mod)

def get_tip_select_tag():
    mod = get_mod_key()
    return _("Select Tag for Finding Matches ({mod}T)\nSelect a tag to use when finding closest matches for the selected person.").format(mod=mod)

def get_tip_find_path():
    mod = get_mod_key()
    return _("Paths ({mod}P)\nShow relationship paths between the selected person and a target person. The first time you enter Paths mode, choose the target person.").format(mod=mod)

TIP_TOP_N = _(
    "Number of Results\n"
    "Specify how many results to return when finding the closest"
    " people who are tagged as well as the number of paths"
    " between the selected person and the home person."
)
TIP_MAX_DEPTH = _(
    "Maximum Depth For Finding Relationships\n"
    "Specify how far to search within the tree for tagged matches"
    " and relationship paths between two people."
    " Higher values will find more distant connections but will"
    " take longer to find in large trees. Reasonable values are"
    " 10 for fast searching or 50 to find very distant but often"
    " interesting paths between people in your tree. To change this"
    " setting permanently, alter it in the preferences window."
)
TIP_FUZZY_THRESHOLD = _(
    "Fuzzy Threshold\n"
    "Similarity cutoff for fuzzy name search, from 0.00 to 1.00."
    " Lower values allow more matches; higher values are stricter."
)
TIP_MAX_DISPLAY = _(
    "Maximum Search Results\n"
    "Maximum number of people shown in the search results list."
    " Higher values may slow down filtering in very large trees."
)

def get_tip_dna_flagged_only():
    mod = get_mod_key()
    return _("Toggle Tagged Only ({mod}D)\nWhen checked, only people flagged as tagged will be shown in search results. Default Tags are DNA-related, but you can set other tag terms. Default is unchecked to show all people, but checking this focusses on tagged matches in large trees.").format(mod=mod)

def get_tip_fuzzy():
    mod = get_mod_key()
    return _("Toggle Fuzzy Search ({mod}U)\nAllow fuzzy name matching in search results. Fuzzy matching uses a similarity ratio to find names similar to the search term, which can help find matches when names are misspelled, have minor variations, or use cached Hebrew/Cyrillic transliterated aliases.").format(mod=mod)

def get_tip_married_names():
    display = _shortcut_by_action('toggle_married_name_search').display
    return _("Toggle Married Names ({display})\nInclude women's married names in Find searches by combining each woman's given name with the last names of her husbands.").format(display=display)

# ---------------------------------------------------------------------------
# Profile window
# ---------------------------------------------------------------------------
WIN_GEDCOM_RECORD = _("GEDCOM Record: {name}")
BIO_SECTION = _("Biography")
BIO_BORN = _("  Born:    {event}")
BIO_MARRIED = _("  Married: {spouses}")
BIO_DIED = _("  Died:    {event}")
BIO_BURIED = _("  Buried:  {event}")
BIO_AGE = _("  Age:     {age}")
BIO_AGE_AT_DEATH = _("  Age:     {age} (at death)")
BIO_NO_INFO = _("  (no biographical information found)")
FAM_SECTION = _("Family")
FAM_PARENTS = _("  Parents:")
FAM_SIBLINGS = _("  Siblings:")
FAM_SPOUSE = _("  Spouse:")
FAM_SPOUSES = _("  Spouses:")
FAM_CHILDREN = _("  Children:")
FAM_NO_INFO = _("  (no family information found)")
FAM_ROLE_FATHER = _("Father")
FAM_ROLE_MOTHER = _("Mother")
FAM_ROLE_PARENT = _("Parent")
FAM_ROLE_STEP_FATHER = _("Step-father")
FAM_ROLE_STEP_MOTHER = _("Step-mother")
FAM_ROLE_STEP_PARENT = _("Step-parent")
FAM_ROLE_ADOPTIVE_FATHER = _("Adoptive father")
FAM_ROLE_ADOPTIVE_MOTHER = _("Adoptive mother")
FAM_ROLE_ADOPTIVE_PARENT = _("Adoptive parent")
FAM_ROLE_FOSTER_FATHER = _("Foster father")
FAM_ROLE_FOSTER_MOTHER = _("Foster mother")
FAM_ROLE_FOSTER_PARENT = _("Foster parent")
FAM_ROLE_SON = _("Son")
FAM_ROLE_DAUGHTER = _("Daughter")
FAM_ROLE_CHILD = _("Child")
FAM_ROLE_STEP_SON = _("Step-son")
FAM_ROLE_STEP_DAUGHTER = _("Step-daughter")
FAM_ROLE_STEP_CHILD = _("Step-child")
FAM_ROLE_ADOPTED_SON = _("Adopted son")
FAM_ROLE_ADOPTED_DAUGHTER = _("Adopted daughter")
FAM_ROLE_ADOPTED_CHILD = _("Adopted child")
FAM_ROLE_FOSTER_SON = _("Foster son")
FAM_ROLE_FOSTER_DAUGHTER = _("Foster daughter")
FAM_ROLE_FOSTER_CHILD = _("Foster child")
FAM_ROLE_BROTHER = _("Brother")
FAM_ROLE_SISTER = _("Sister")
FAM_ROLE_SIBLING = _("Sibling")
FAM_ROLE_HALF_BROTHER = _("Half-brother")
FAM_ROLE_HALF_SISTER = _("Half-sister")
FAM_ROLE_HALF_SIBLING = _("Half-sibling")
FAM_ROLE_STEP_BROTHER = _("Step-brother")
FAM_ROLE_STEP_SISTER = _("Step-sister")
FAM_ROLE_STEP_SIBLING = _("Step-sibling")
FAM_ROLE_ADOPTIVE_SIBLING = _("Adoptive sibling")
FAM_ROLE_FOSTER_SIBLING = _("Foster sibling")
FAM_MEMBER_ROLE_PREFIX = _("    {role}: ")
TAGS_SECTION = _("Tags")
GEDCOM_SECTION = _("Full GEDCOM Record")
BTN_CLOSE = _("Close")
BTN_TREE_VIEW = _("Tree View")
BTN_PEDIGREE_VIEW = _("Pedigree View")
BTN_DESCENDANT_VIEW = _("Descendant View")
BTN_PERSON_VIEW = _("Profile View")

def get_tip_tree_view_btn():
    mod = get_mod_key()
    return _("Tree View ({mod}T cycles views)\nShow the interactive family tree for this person.").format(mod=mod)

def get_tip_pedigree_view_btn():
    mod = get_mod_key()
    return _("Pedigree View ({mod}T cycles views)\nShow this person's ancestors in a compact pedigree chart.").format(mod=mod)

def get_tip_descendant_view_btn():
    mod = get_mod_key()
    return _("Descendant View ({mod}T cycles views)\nShow this person's descendants with expandable child branches.").format(mod=mod)

def get_tip_person_view_btn():
    mod = get_mod_key()
    return _("Profile View ({mod}T cycles views)\nShow the biographical profile for this person.").format(mod=mod)

DLG_SAVE_PROFILE = _("Save profile")

def get_tip_save_profile():
    mod = get_mod_key()
    return _("Save profile ({mod}S)\nSave this biographical profile to a text file.").format(mod=mod)

def get_tip_copy_profile():
    mod = get_mod_key()
    return _("Copy profile ({mod}C)\nCopy this biographical profile to clipboard.").format(mod=mod)

WIN_FAMILY_TREE = _("Family Tree: {name}")
WIN_PEDIGREE_TREE = _("Pedigree Tree: {name}")
WIN_DESCENDANT_TREE = _("Descendant Tree: {name}")
DLG_SAVE_FAMILY_TREE = _("Save family tree")
DLG_SAVE_PEDIGREE_TREE = _("Save pedigree tree")
DLG_SAVE_DESCENDANT_TREE = _("Save descendant tree")
TREE_MENU_RECENTER = _("Center")
TREE_MENU_PATHS = _("Paths")
TREE_MENU_EXPAND_ALL = _("Expand All")
GRAPH_MENU_HIGHLIGHT = _("Highlight")
TREE_BUTTON_PARENTS = "↑"
TREE_BUTTON_PARENTS_HIDE = "↓"
TREE_BUTTON_SIBLINGS_LEFT = "←"
TREE_BUTTON_SIBLINGS_RIGHT = "→"
TREE_BUTTON_SPOUSES = "♥"
TREE_BUTTON_SPOUSES_HIDE = "♡"
TREE_BUTTON_CHILDREN = "↓"
TREE_BUTTON_CHILDREN_HIDE = "↑"
GRAPH_LEGEND_BIOLOGICAL = _("biological")
GRAPH_LEGEND_STEP = _("step")
GRAPH_LEGEND_ADOPTED_FOSTER = _("adopted/foster")
GRAPH_LEGEND_HALF = _("half sibling")

# ---------------------------------------------------------------------------
# DNA match results display
# ---------------------------------------------------------------------------
RESULT_CLOSEST_MATCHES = _("Closest Tagged Matches")
RESULT_DNA_FLAGGED_NOTE = _("  Note: this person has a matching tag.")
RESULT_NO_DNA_FOUND = _("No tagged relatives found within the search depth.")
RESULT_RANK_PREFIX = _("#{rank}: ")
RESULT_DNA_MARKERS = _("   Tags:")
RESULT_RELATIONSHIP = _("Relationship: {rel}")
TIP_RELATIONSHIP = _("Show relationship graphically")
RESULT_COMMON_ANCESTOR = _("Common ancestor: ")
RESULT_COMMON_ANCESTORS = _("Common ancestors:")
RESULT_COMMON_ANCESTOR_NONE = _("None found.")
RESULT_PATH = _("Path:")
RESULT_PATH_SECTION = _("Path to Home Person")
RESULT_HOME = _("Home: ")
RESULT_HOME_PATH_LOADING = _("Calculating path…")
RESULT_NO_HOME_PATH = _("None found within the current max depth.")

EDGE_LABELS = {
    'father': _('father'),
    'mother': _('mother'),
    'sibling': _('sibling'),
    'spouse': _('spouse'),
    'child': _('child'),
}
WIN_PATH_GRAPH = _("Relationship Graph")
DLG_SAVE_RESULTS = _("Save results")
DLG_SAVE_GRAPH = _("Save relationship graph")
DLG_SAVE_GRAPH_DEBUG = _("Save graph layout debug data")
PATH_GRAPH_MENU_SHOW_TREE = _("Show Tree")
PATH_GRAPH_MENU_FIND_PATH = _("Find Path")
RESULTS_HEADER_MENU_COPY_NAME = _("Copy Name")
RESULTS_HEADER_MENU_SHOW_PROFILE = _("Show Profile")
RESULTS_HEADER_MENU_SHOW_TREE = _("Show Tree")
BTN_SAVE_GRAPH = _("Save")
BTN_COPY_GRAPH = _("Copy")
BTN_SEARCH_GRAPH = _("Search")
BTN_JUMP_GRAPH = _("Jump")
BTN_DEBUG_GRAPH = _("Debug JSON")

def get_tip_save_graph():
    mod = get_mod_key()
    return _("Save graphic ({mod}S)\nSave this graphical representation to a file.").format(mod=mod)

def get_tip_copy_graph():
    mod = get_mod_key()
    return _("Copy graphic ({mod}C)\nCopy this graphical representation to clipboard.").format(mod=mod)

def get_tip_search_graph():
    mod = get_mod_key()
    return _("Search ({mod}F)\nSelect a person and make them the center of this graphical view.").format(mod=mod)

def get_tip_jump_graph():
    mod = get_mod_key()
    return _("Jump ({mod}J)\nPan to a person who is already visible in this graph view.").format(mod=mod)

TIP_DEBUG_GRAPH = _("Save layout debug JSON (Ctrl+Shift+D)\nExport graph layout data without person names.")
TIP_SHOW_PARENTS = _("Show parents")
TIP_HIDE_PARENTS = _("Hide parents")
TIP_SHOW_SIBLINGS = _("Show siblings")
TIP_HIDE_SIBLINGS = _("Hide siblings")
TIP_SHOW_SPOUSES = _("Show spouses")
TIP_HIDE_SPOUSES = _("Hide spouses")
TIP_SHOW_CHILDREN = _("Show children")
TIP_HIDE_CHILDREN = _("Hide children")
PATH_GRAPH_START = _("START")
PATH_GRAPH_END = _("END")

# ---------------------------------------------------------------------------
# Relationship path results
# ---------------------------------------------------------------------------
PATH_SECTION = _("Relationship path:")
PATH_FROM = _("  From: ")
PATH_TO = _("  To:   ")
PATH_SAME_PERSON = _("(Same person selected for both.)")
PATH_NOT_FOUND = _("No relationship path found within max depth {depth}.")
PATH_RANK = _("Path #{rank}:")
PATH_SEARCH_CAP = _(
    "(Search cap reached — there may be additional paths. "
    "Reduce Max depth to search a smaller area.)"
)

# ---------------------------------------------------------------------------
# Tag definitions dialog
# ---------------------------------------------------------------------------
WIN_TAG_DEFINITIONS = _("Tag definitions")
MSG_NO_TAGS = _(
    "No _MTTAG records found in the loaded file.\n\n"
    "(If you haven't loaded a file yet, click Load first.)"
)
COL_TAG_ID = _("ID")
COL_TAG_NAME = _("Tag Name")
BTN_OK = _("OK")
BTN_CANCEL = _("Cancel")

# ---------------------------------------------------------------------------
# Pick person dialog
# ---------------------------------------------------------------------------
WIN_SELECT_PERSON = _("Select a Person")
WIN_SELECT_TARGET = _("Select Relationship Target")
BTN_SELECT = _("Select")

# ---------------------------------------------------------------------------
# Preferences dialog
# ---------------------------------------------------------------------------
WIN_PREFERENCES = _("Settings") if sys.platform == 'darwin' else _("Preferences")
FRAME_APPEARANCE = _("Appearance")
FRAME_FONT_SIZE = _("Font size")
FONT_SMALL = _("Small")
FONT_MEDIUM = _("Medium")
FONT_LARGE = _("Large")
FONT_JUMBO = _("Jumbo")
FRAME_THEME = _("Theme")
CHK_HIDE_TOOLTIPS = _("Hide Tooltips")
TIP_HIDE_TOOLTIPS = _("Hide popup explanations like this one.")
FRAME_SEARCH_DEFAULTS = _("Search defaults")
LBL_TOP_N_RESULTS = _("Results:")
LBL_MAX_DEPTH_PREF = _("Max Depth:")
LBL_FUZZY_THRESHOLD = _("Fuzzy threshold:")
LBL_MAX_DISPLAY = _("Max search results:")
FRAME_DISPLAY = _("Display")
CHK_SHOW_IDS = _("Show GEDCOM IDs")
TIP_SHOW_IDS = _(
    "When enabled, the GEDCOM ID for each person is shown in parentheses after their name. "
    "This can help disambiguate people with the same name and allows you to access the raw IDs "
    "for GEDCOM research with other tools."
)
CHK_SHOW_FULL_GEDCOM = _("Show Full GEDCOM")
TIP_SHOW_FULL_GEDCOM = _(
    "When enabled, the Full GEDCOM Record section is included at the bottom of "
    "the Profile window, showing the raw GEDCOM data for the person."
)
LBL_NAME_FORMAT = _("Name format:")
NAME_FIRST_LAST = _("First Last")
NAME_LAST_FIRST = _("Last, First")
LBL_DEFAULT_DISPLAY = _("Default display:")
LBL_DEFAULT_TREE = _("Default tree:")
TREE_MODE_TREE = _("Tree")
TREE_MODE_PEDIGREE = _("Pedigree")
TREE_MODE_DESCENDANTS = _("Descendants")
FRAME_CACHE = _("Cache")
BTN_CLEAR_CACHE = _("Clear Cache…")
LBL_CACHE_NOTE = _("Remove all cached GEDCOM data")
LBL_LANGUAGE = _("Language:")
LANG_SYSTEM = _("System Default")
LBL_LANGUAGE_CHANGED = _("Language Changed")
MSG_LANGUAGE_CHANGED = _("Language changed from {old} to {new}. Please restart the application for the change to take effect.")

# ---------------------------------------------------------------------------
# Search progress popup
# ---------------------------------------------------------------------------
PROGRESS_SEARCHING_TITLE = _("Searching")
PROGRESS_SEARCHING = _("Searching for tagged matches…\n(reduce 'max depth' setting for faster search)")
PROGRESS_FINDING_PATH = _("Finding relationship paths…\n(reduce 'max depth' setting for faster search)")
PROGRESS_EXPANDING_DESCENDANTS = _("Expanding descendant branches…")

# ---------------------------------------------------------------------------
# Status bar messages
# ---------------------------------------------------------------------------
STATUS_LOADING = _("Loading…")
STATUS_LOAD_FAILED = _("Load failed.")
STATUS_LOADED_CACHED = _("Loaded {count:,} individuals (from cache).")
STATUS_LOADED = _("Loaded {count:,} individuals.")
STATUS_SHOWING_FIRST = _(
    "Showing first {max_display:,} of {total_matches:,} matches. "
    "Refine your search.  ({total:,} total, {flagged} tagged)"
)
STATUS_MATCHES = _("{shown:,} match{plural} shown.  ({total:,} total, {flagged} tagged)")
STATUS_OVERVIEW = _(
    "{total:,} individuals, {families:,} families, "
    "{flagged} tagged.  Type to search."
)
STATUS_HOME_SET = _("Home person set: {name}")

# ---------------------------------------------------------------------------
# Error / warning dialogs
# ---------------------------------------------------------------------------
ERR_NO_FILE_TITLE = _("No file")
ERR_NO_FILE_MSG = _("Please choose a GEDCOM file first.")
ERR_NOT_FOUND_TITLE = _("Not found")
ERR_NOT_FOUND_MSG = _("File not found:\n{path}")
ERR_ZIP_TITLE = _("ZIP error")
ERR_ZIP_MSG = _("Could not extract GEDCOM from ZIP:\n\n{error}")
ERR_PARSE_TITLE = _("Parse error")
ERR_PARSE_MSG = _("Error reading GEDCOM:\n\n{error}")
ERR_ENCODING_TITLE = _("Encoding warning")
ERR_NO_DATA_TITLE = _("No data")
ERR_NO_DATA_MSG = _("Load a GEDCOM file first.")
ERR_NO_SEL_TITLE = _("No selection")
ERR_NO_SEL_MSG = _("Select a person from the list first.")
ERR_BAD_VAL_TITLE = _("Bad value")
ERR_BAD_VAL_TOP_N = _("Results and Max Depth must be integers.")
ERR_BAD_VAL_DEPTH = _("Max Depth must be an integer.")
ERR_NO_PATH_SEL_MSG = _("Select a starting person from the main list first.")
ERR_FILE_NOT_FOUND_TITLE = _("File not found")
ERR_FILE_NOT_FOUND_MSG = _("Could not open:\n{path}\n\n{error}")
ERR_SAVE_GRAPH_TITLE = _("Save error")
ERR_SAVE_GRAPH_MSG = _("Could not save relationship graph:\n\n{error}")
ERR_COPY_GRAPH_TITLE = _("Copy error")
ERR_COPY_GRAPH_MSG = _("Could not copy relationship graph:\n\n{error}")
ERR_SAVE_GRAPH_DEBUG_MSG = _("Could not save graph layout debug data:\n\n{error}")
ERR_SAVE_RESULTS_MSG = _("Could not save results:\n\n{error}")
ERR_SAVE_PROFILE_MSG = _("Could not save profile:\n\n{error}")
ERR_GEDCOM_NOT_FOUND_MSG = _(
    "GEDCOM file not found:\n{path}\n\n"
    "Use Browse… to choose a different file."
)

# ---------------------------------------------------------------------------
# Cache dialogs
# ---------------------------------------------------------------------------
CACHE_EMPTY_TITLE = _("Cache")
CACHE_EMPTY_MSG = _("No cache files found.")
CACHE_CLEAR_TITLE = _("Clear cache")
CACHE_CLEAR_MSG = _(
    "Delete {count} cached file(s)?\n\n"
    "Note: the cache may contain personal information and raw records "
    "from your GEDCOM files."
)
CACHE_DONE_TITLE = _("Cache cleared")
CACHE_DONE_MSG = _("{deleted} file(s) deleted.")

# ---------------------------------------------------------------------------
# Info windows
# ---------------------------------------------------------------------------
WIN_HOW_TO_USE = _("How to Use")
WIN_KEYBOARD_SHORTCUTS = _("Keyboard Shortcuts")
WIN_ABOUT = _("About")
WIN_PRIVACY_POLICY = _("Privacy Policy")
WIN_CHECKING_FOR_UPDATES = _("Checking for Updates")
WIN_UPDATE_AVAILABLE = _("Update Available")

# ---------------------------------------------------------------------------
# Welcome window and interactive walkthrough
# ---------------------------------------------------------------------------
WIN_WELCOME = _("Welcome to GEDCOM Navigator")
CHK_SHOW_NEXT_TIME = _("Show this window next time")
BTN_WALKTHROUGH = _("Walkthrough")
BTN_WT_NEXT = _("Next")
BTN_WT_BACK = _("Back")
BTN_WT_SKIP = _("Skip")
BTN_WT_FINISH = _("Finish")

# Coach-mark text for the areas that have no existing tooltip. Each entry is a
# (title, body) pair; widgets that already carry a tooltip reuse that text.
WT_LIST_TITLE = _("People list")
WT_LIST_BODY = _(
    "Everyone in your GEDCOM file appears here. Select a person to view "
    "their profile, find DNA matches, or trace relationship paths.")
WT_RESULTS_TITLE = _("Results pane")
WT_RESULTS_BODY = _(
    "Profiles, tag matches (such as DNA), and relationship paths are shown here. "
    "Names and relationship descriptions in this pane are clickable.")
WT_STATUS_TITLE = _("Status bar")
WT_STATUS_BODY = _(
    "Shows the loaded file and progress, and holds the Save and Copy buttons "
    "for the current results.")
WT_PERSON_LINK_TITLE = _("Clickable names")
WT_PERSON_LINK_BODY = _(
    "Click any person's name in the results to jump to their profile. Use the "
    "Use Back and Forward keyboard shortcuts to retrace your steps.")
WT_REL_LINK_TITLE = _("Clickable relationships")
WT_REL_LINK_BODY = _(
    "Click an underlined relationship description to open it as a relationship "
    "graph showing how the two people are connected.")
WT_MODES_TITLE = _("Display modes")
WT_MODES_BODY = _(
    "Switch the right pane between Profile, Tag Matches (e.g. DNA Tags), "
    "and Relationship Paths for the selected person. Selecting 'Paths' "
    "will prompt you to choose another person to find paths to.")
WT_MATCHES_SETTINGS_TITLE = _("Match tag settings")
WT_MATCHES_SETTINGS_BODY = _(
    "In Matches mode, set the tag keyword and page marker that identify "
    "tagged people (e.g. 'DNA'), or pick an existing tag from your file.")
WT_NODE_MENU_TITLE = _("Tree View menu")
WT_NODE_MENU_BODY = _(
    "Right-click (or click) any person in the tree view for quick actions: "
    "{items}.")
WT_SAMPLE_NOTICE = _(
    "A sample family tree has been loaded so you can try these features. It "
    "will be unloaded when the walkthrough ends.")

COL_SHORTCUT = _("Shortcut")
COL_ACTION = _("Action")

UPDATE_CHECKING_MSG = _("Checking GitHub for the latest release…")
UPDATE_CHECK_FAILED_TITLE = _("Update check failed")
UPDATE_CHECK_FAILED_MSG = _("Could not check for updates right now.\n\n{error}")
UPDATE_CURRENT_TITLE = _("No update available")
UPDATE_CURRENT_MSG = _("You are running the latest version ({current}).")
UPDATE_AVAILABLE_HEADING = _("A newer version is available.")
UPDATE_INSTALLED_VERSION = _("Installed version: {current}")
UPDATE_LATEST_VERSION = _("Latest version: {latest}")
UPDATE_DOWNLOAD_PROMPT = _("Download the latest release from GitHub:")
UPDATE_OPEN_RELEASES = _("Open GitHub Releases")

# ---------------------------------------------------------------------------
# File association
# ---------------------------------------------------------------------------
FILE_ASSOC_PROMPT_TITLE = _("Set as Default")
FILE_ASSOC_PROMPT_MSG = _(
    "Would you like GEDCOM Navigator to open .ged files by default?")
FILE_ASSOC_FAILED_TITLE = _("Could Not Set Default")
FILE_ASSOC_FAILED_MSG = _(
    "GEDCOM Navigator could not register as the default .ged handler.")

def get_keyboard_shortcut_rows():
    actions = {
        "help": _("Help"),
        "keyboard_shortcuts": _("Keyboard Shortcuts"),
        "preferences": _("Open Preferences"),
        "find_person": _("Find Person"),
        "filter_results": _("Filter Results"),
        "toggle_tagged_filter": _("Toggle the tagged filter"),
        "toggle_fuzzy_search": _("Toggle fuzzy search mode"),
        "toggle_married_name_search": _("Toggle married-name search mode"),
        "open_gedcom": _("Open a new GEDCOM file"),
        "display_matches": _("Switch the Display Pane to Matches"),
        "display_tree": _("Open Tree View for selected person"),
        "set_home": _("Set Home person to the selected person"),
        "display_paths": _("Switch the Display Pane to Paths"),
        "select_tag": _("Select new tag for finding relationship paths"),
        "reverse_results": _(
            "Reverse/restore the direction of all relationship paths"),
        "save_results": _("Save results to a text file"),
        "copy_results": _("Copy result to clipboard"),
        "back": _("Go back to the previous view"),
        "forward": _("Go forward to the next view"),
        "zoom_in_out": _("Zoom the focused text or graph view"),
        "zoom_reset": _("Reset zoom in the focused text or graph view"),
    }
    return [
        (shortcut.display, actions[shortcut.action_key])
        for shortcut in _shortcut_rows(sys.platform)
    ]
