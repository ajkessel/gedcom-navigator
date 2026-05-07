"""
gedcom_strings.py

All English-language strings displayed to the user by gedcom_dna_finder_gui.py.

To translate the application, copy this file (e.g. gedcom_strings_fr.py),
replace the string values, and import that module instead of this one.

Strings that include runtime values use str.format() placeholders, e.g.
    STATUS_LOADED.format(count=42)
"""

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
APP_TITLE = "GEDCOM DNA Match Finder"
STATUS_NO_FILE = "No file loaded."

# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
MENU_MENU = "Menu"
MENU_PREFERENCES = "Preferences…"
MENU_CLEAR_CACHE = "Clear cache…"
MENU_HOW_TO_USE = "How to use"
MENU_KEYBOARD_SHORTCUTS = "Keyboard shortcuts"
MENU_PRIVACY_POLICY = "Privacy Policy"
MENU_ABOUT = "About"
MENU_QUIT = "Quit"

# ---------------------------------------------------------------------------
# File panel
# ---------------------------------------------------------------------------
FRAME_GEDCOM_FILE = "GEDCOM file"
BTN_BROWSE = "Browse…"
DLG_SELECT_GEDCOM = "Select GEDCOM file"

# ---------------------------------------------------------------------------
# DNA marker settings panel
# ---------------------------------------------------------------------------
FRAME_DNA_SETTINGS = "DNA marker settings"
LBL_TAG_KEYWORD = "Tag keyword:"
LBL_PAGE_MARKER = "Page marker:"
BTN_SELECT_TAG = "Select Tag"
BTN_FIND_PATH = "Find Relationship Path"

# ---------------------------------------------------------------------------
# People list
# ---------------------------------------------------------------------------
LBL_FIND = "Find:"
CHK_DNA_FLAGGED_ONLY = "DNA-flagged only"
CHK_FUZZY = "Fuzzy"
LBL_FILTER = "Filter:"
COL_NAME = "Name"
COL_BIRTH = "Birth"
COL_DEATH = "Death"
COL_DNA = "DNA?"

# ---------------------------------------------------------------------------
# Action controls (main window)
# ---------------------------------------------------------------------------
LBL_TOP_N = "Top N:"
LBL_MAX_DEPTH = "Max depth:"
BTN_FIND_MATCHES = "Find Nearest DNA Matches"
BTN_SHOW_PERSON = "Show Person"
BTN_SET_HOME = "Set Home"

# ---------------------------------------------------------------------------
# Results panel
# ---------------------------------------------------------------------------
LBL_RESULTS = "Results:"
BTN_COPY = "Copy"

# ---------------------------------------------------------------------------
# Tooltips
# ---------------------------------------------------------------------------
TIP_BROWSE = (
    "Browse to select a GEDCOM file. You can also select a ZIP file containing a GEDCOM."
)
TIP_FIND = (
    "Find (Ctrl+F)\n"
    "Type to filter the list of people. Search by any name variation. Use the filter box "
    "to search by other information in a person's GEDCOM record, such as geographic location. "
    "Press Enter to jump directly to the first match. "
    "Use the checkboxes to show only DNA-flagged people and to allow fuzzy name matching."
)
TIP_FILTER = (
    "Filter (Ctrl+I)\n"
    "Type to filter the list of people by any information in their GEDCOM record, "
    "such as geographic location. This filter is applied in addition to the Find box above."
)   
TIP_TAG_KEYWORD = (
    "Enter a keyword to filter the list of tags used for finding relationship paths. "
    "Leave this blank to use only the page marker keyword to find relationship paths."
)
TIP_PAGE_MARKER = (
    "Enter a unique keyword to use as a page marker when finding relationship paths. "
    "Leave this blank to use only the tag keyword to find relationship paths."
)
TIP_SELECT_TAG = (
    "Select Tag for Finding Paths (Ctrl+T)\n"
    "Select a new tag for finding the path between the selected person"
    " and the closest people with that tag."
)
TIP_FIND_PATH = (
    "Find Relationship Paths (Ctrl+P)\n"
    "Find multiple paths between the selected person and any other"
    " person in your tree."
)
TIP_TOP_N = (
    "Top N Results\n"
    "Specify how many results to return when finding the closest"
    " people who are DNA matches as well as the number of paths"
    " between the selected person and the home person."
)
TIP_MAX_DEPTH = (
    "Maximum Depth For Finding Relationships\n"
    "Specify how far to search within the tree for closest DNA"
    " matches and for the relationship between two people."
    " Higher values will find more distant connections but will"
    " take longer to find in large trees."
)
TIP_FUZZY_THRESHOLD = (
    "Fuzzy Threshold\n"
    "Similarity cutoff for fuzzy name search, from 0.00 to 1.00."
    " Lower values allow more matches; higher values are stricter."
)
TIP_DNA_FLAGGED_ONLY = (
    "Toggle DNA-flagged Only (Ctrl+D)\n"
    "When checked, only people flagged as DNA matches will be shown in search results."
)
TIP_FUZZY = (
    "Toggle Fuzzy Search (Ctrl+U)\n"
    "Allow fuzzy name matching in search results. "
    "Fuzzy matching uses the Levenshtein distance to find names similar to the search term, "
    "which can help find matches when names are misspelled or have minor variations."
)

# ---------------------------------------------------------------------------
# Show Person window
# ---------------------------------------------------------------------------
WIN_GEDCOM_RECORD = "GEDCOM Record: {name}"
BIO_SECTION = "Biography"
BIO_BORN = "  Born:    {event}"
BIO_MARRIED = "  Married: {spouses}"
BIO_DIED = "  Died:    {event}"
BIO_BURIED = "  Buried:  {event}"
BIO_NO_INFO = "  (no biographical information found)"
FAM_SECTION = "Family"
FAM_PARENTS = "  Parents:"
FAM_SIBLINGS = "  Siblings:"
FAM_CHILDREN = "  Children:"
FAM_NO_INFO = "  (no family information found)"
GEDCOM_SECTION = "Full GEDCOM Record"
BTN_CLOSE = "Close"

# ---------------------------------------------------------------------------
# DNA match results display
# ---------------------------------------------------------------------------
RESULT_STARTING_FROM = "Closest tag matches starting from "
RESULT_DNA_FLAGGED_NOTE = "  Note: this person is themselves DNA-flagged."
RESULT_NO_DNA_FOUND = "No DNA-flagged relatives found within the search depth."
RESULT_RANK_PREFIX = "#{rank}: "
RESULT_DISTANCE = " (distance: {dist} edges)"
RESULT_DNA_MARKERS = "   DNA markers:"
RESULT_RELATIONSHIP = "   Relationship: {rel}"
RESULT_PATH = "   Path:"
RESULT_EDGE = "       --[{edge}]--> "
RESULT_PATH_SECTION = "Path to Home Person"
RESULT_HOME = "Home: "
RESULT_NO_HOME_PATH = "No path found to home person within the current max depth."
RESULT_HOME_REL = "Relationship: {rel} ({dist} edge{plural})"
RESULT_HOME_PATH = "Path:"
RESULT_HOME_EDGE = "    --[{edge}]--> "

# ---------------------------------------------------------------------------
# Relationship path results
# ---------------------------------------------------------------------------
PATH_SECTION = "Relationship path:"
PATH_FROM = "  From: "
PATH_TO = "  To:   "
PATH_SAME_PERSON = "(Same person selected for both.)"
PATH_NOT_FOUND = "No relationship path found within max depth {depth}."
PATH_RANK = "Path #{rank} — {rel} ({dist} edge{plural}):"
PATH_EDGE = "    --[{edge}]--> "
PATH_SEARCH_CAP = (
    "(Search cap reached — there may be additional paths. "
    "Reduce Max depth to search a smaller area.)"
)

# ---------------------------------------------------------------------------
# Tag definitions dialog
# ---------------------------------------------------------------------------
WIN_TAG_DEFINITIONS = "Tag definitions"
MSG_NO_TAGS = (
    "No _MTTAG records found in the loaded file.\n\n"
    "(If you haven't loaded a file yet, click Load first.)"
)
COL_TAG_ID = "ID"
COL_TAG_NAME = "Tag Name"
BTN_OK = "OK"
BTN_CANCEL = "Cancel"

# ---------------------------------------------------------------------------
# Pick person dialog
# ---------------------------------------------------------------------------
WIN_SELECT_PERSON = "Select a Person"
WIN_SELECT_TARGET = "Select Relationship Target"
BTN_SELECT = "Select"

# ---------------------------------------------------------------------------
# Preferences dialog
# ---------------------------------------------------------------------------
WIN_PREFERENCES = "Preferences"
FRAME_FONT_SIZE = "Font size"
FONT_SMALL = "Small"
FONT_MEDIUM = "Medium"
FONT_LARGE = "Large"
FRAME_THEME = "Theme"
FRAME_SEARCH_DEFAULTS = "Search defaults"
LBL_TOP_N_RESULTS = "Top N results:"
LBL_MAX_DEPTH_PREF = "Max depth:"
LBL_FUZZY_THRESHOLD = "Fuzzy threshold:"
FRAME_DISPLAY = "Display"
CHK_SHOW_IDS = "Show IDs (person and tag ID codes from GEDCOM)"
LBL_NAME_FORMAT = "Name format:"
NAME_FIRST_LAST = "First Last"
NAME_LAST_FIRST = "Last, First"
FRAME_CACHE = "Cache"
BTN_CLEAR_CACHE = "Clear Cache…"
LBL_CACHE_NOTE = "Remove all cached GEDCOM data"

# ---------------------------------------------------------------------------
# Status bar messages  (use .format() to fill in placeholders)
# ---------------------------------------------------------------------------
STATUS_EXTRACTED_ZIP = "Extracted {name} from ZIP…"
STATUS_LOADING = "Loading…"
STATUS_LOAD_FAILED = "Load failed."
STATUS_LOADED_CACHED = "Loaded {count:,} individuals (from cache)."
STATUS_LOADED = "Loaded {count:,} individuals."
STATUS_SHOWING_FIRST = (
    "Showing first {max_display:,} of more matches. "
    "Refine your search.  ({total:,} total, {flagged} DNA-flagged)"
)
STATUS_MATCHES = "{shown:,} match{plural} shown.  ({total:,} total, {flagged} DNA-flagged)"
STATUS_OVERVIEW = (
    "{total:,} individuals, {families:,} families, "
    "{flagged} DNA-flagged.  Type to search."
)
STATUS_HOME_SET = "Home person set: {name}"

# ---------------------------------------------------------------------------
# Error / warning dialogs  (title, message pairs)
# ---------------------------------------------------------------------------
ERR_NO_FILE_TITLE = "No file"
ERR_NO_FILE_MSG = "Please choose a GEDCOM file first."
ERR_NOT_FOUND_TITLE = "Not found"
ERR_NOT_FOUND_MSG = "File not found:\n{path}"
ERR_ZIP_TITLE = "ZIP error"
ERR_ZIP_MSG = "Could not extract GEDCOM from ZIP:\n\n{error}"
ERR_PARSE_TITLE = "Parse error"
ERR_PARSE_MSG = "Error reading GEDCOM:\n\n{error}"
ERR_ENCODING_TITLE = "Encoding warning"
ERR_NO_DATA_TITLE = "No data"
ERR_NO_DATA_MSG = "Load a GEDCOM file first."
ERR_NO_SEL_TITLE = "No selection"
ERR_NO_SEL_MSG = "Select a person from the list first."
ERR_BAD_VAL_TITLE = "Bad value"
ERR_BAD_VAL_TOP_N = "Top N and Max depth must be integers."
ERR_BAD_VAL_DEPTH = "Max depth must be an integer."
ERR_NO_PATH_SEL_MSG = "Select a starting person from the main list first."
ERR_FILE_NOT_FOUND_TITLE = "File not found"
ERR_FILE_NOT_FOUND_MSG = "Could not open:\n{path}\n\n{error}"
ERR_GEDCOM_NOT_FOUND_MSG = (
    "GEDCOM file not found:\n{path}\n\n"
    "Use Browse… to choose a different file."
)

# ---------------------------------------------------------------------------
# Cache dialogs
# ---------------------------------------------------------------------------
CACHE_EMPTY_TITLE = "Cache"
CACHE_EMPTY_MSG = "No cache files found."
CACHE_CLEAR_TITLE = "Clear cache"
CACHE_CLEAR_MSG = (
    "Delete {count} cached file(s)?\n\n"
    "Note: the cache may contain personal information (names, dates) "
    "from your GEDCOM files."
)
CACHE_DONE_TITLE = "Cache cleared"
CACHE_DONE_MSG = "{deleted} file(s) deleted."

# ---------------------------------------------------------------------------
# Info windows
# ---------------------------------------------------------------------------
WIN_HOW_TO_USE = "How to use"
WIN_KEYBOARD_SHORTCUTS = "Keyboard shortcuts"
WIN_ABOUT = "About"
WIN_PRIVACY_POLICY = "Privacy Policy"

COL_SHORTCUT = "Shortcut"
COL_ACTION = "Action"

KEYBOARD_SHORTCUT_ROWS = [
    ("Esc",      "Close any dialog or pop-up window"),
    ("Ctrl+F",   "Jump to the Search box and select all text"),
    ("Ctrl+I",   "Jump to the Filter box and select all text"),
    ("Ctrl+D",   "Toggle the DNA-flagged only filter"),
    ("Ctrl+U",   "Toggle Fuzzy search mode"),
    ("Ctrl+O",   "Open the file browser (Browse…)"),
    ("Ctrl+N",   "Find Nearest DNA Matches for the selected person"),
    ("Ctrl+S",   "Show the raw GEDCOM record for the selected person"),
    ("Ctrl+H",   "Set Home person to the selected person"),
    ("Ctrl+P",   "Open the Find Relationship Path dialog"),
    ("Ctrl+T",   "View tag definitions"),
    ("Ctrl+C",   "Copy all results to the clipboard"),
    ("Ctrl+L",   "Clear the results pane"),
    ("Alt+M",    "Open the Menu"),
    ("Home",     "Jump to the first item in the search results"),
    ("End",      "Jump to the last item in the search results"),
]

NOTE_KEYBOARD_SHORTCUTS = (
    "Note: Ctrl+C copies the entire results pane. "
    "When the results text area has keyboard focus, "
    "Ctrl+C copies only the selected text as usual."
)
