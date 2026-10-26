from collections import Counter  # Counts how often each value appears
from dataclasses import dataclass  # Simple way to define a data container

from langchain_core.tools import tool  # Turns a Python function into a tool the AI can call

import ingest  # Shared file reading (same column cleaning as the database)

MAX_CATEGORIES = 25  # Columns with this many different values or fewer are listed as categories
MAX_ROWS_SHOWN = 200  # Never show more rows than this in one answer


@dataclass
class Table:  # One sheet of a spreadsheet, fully loaded
    file: str  # File name, e.g. "sites.xlsx"
    sheet: str | None  # Sheet name (None for CSV files)
    headers: list[str]  # Column names that have at least one value
    rows: list[tuple[int, dict[str, str]]]  # (row number in the file, {column: value})

    @property
    def name(self):  # Readable name, e.g. "sites.xlsx / Sheet1"
        return self.file + (f" / {self.sheet}" if self.sheet else "")  # Add the sheet if there is one


_cache = {}  # File path -> (last modified time, tables), so files are only re-read when they change


def load_tables():  # Reads every spreadsheet in the documents folder
    tables = []  # All sheets of all files
    for path in ingest.find_files():  # Every supported file
        if path.suffix.lower() not in ingest.TABLE_EXTENSIONS:  # Not a spreadsheet
            continue  # Skip it
        mtime = path.stat().st_mtime  # When the file last changed
        if _cache.get(str(path), (None,))[0] != mtime:  # Not read yet, or changed since
            sheets = []  # Tables in this file
            for sheet, grid in ingest.read_tables(path):  # Every sheet
                headers, rows = ingest.table_rows(grid)  # Clean column names and rows
                data = [(n, dict(zip(headers, cells))) for n, cells in rows]  # Pair each value with its column
                used = [h for h in headers if any(r.get(h) for _, r in data)]  # Ignore columns that are completely empty
                if data:  # The sheet has rows
                    sheets.append(Table(path.name, sheet, used, data))  # Keep it
            _cache[str(path)] = (mtime, sheets)  # Remember it
        tables += _cache[str(path)][1]  # Add this file's sheets
    return tables  # Hand back everything


def category_counts(values):  # Counts values, treating "Streamer", "streamer" and "STREAMER" (or "Sticker Wraps"/"Stickerwraps") as one
    groups = {}  # Simplified value -> Counter of the original spellings
    for v in values:  # Every value
        groups.setdefault("".join(v.lower().split()), Counter())[v] += 1  # Group ignoring case and spaces
    counts = Counter({spellings.most_common(1)[0][0]: sum(spellings.values()) for spellings in groups.values()})  # Show the most used spelling
    return counts  # Value -> number of rows


def overview(tables=None):  # Text summary of every spreadsheet: columns and their categories
    tables = load_tables() if tables is None else tables  # Use the given tables, or load them
    lines = []  # Summary lines
    for t in tables:  # Every sheet
        lines.append(f"### {t.name} ({len(t.rows)} rows)")  # Title with row count
        for h in t.headers:  # Every column
            values = category_counts(r[h] for _, r in t.rows if r.get(h))  # How often each value appears
            filled = sum(values.values())  # How many rows have a value
            if len(values) <= MAX_CATEGORIES:  # Few different values: it's a category column
                detail = ", ".join(f"{v[:40]} ({c})" for v, c in values.most_common())  # e.g. "Billboard (312), Lampost (95)"
            elif values.most_common(1)[0][1] > 1:  # Many values, but some repeat (e.g. tenant names per month)
                detail = f"{len(values)} different values; most common: " + ", ".join(f"{v[:40]} ({c})" for v, c in values.most_common(5))  # Top 5
            else:  # Every value is different (codes, coordinates...)
                detail = f"{len(values)} different values, e.g. " + "; ".join(v[:40] for v in list(values)[:3])  # A few examples
            lines.append(f"- {h} [{filled} filled]: {detail}")  # One line per column
    return "\n".join(lines)  # Hand back the summary


def find_column(table, name):  # Finds a column by name, forgiving upper/lower case and partial names
    lowered = name.strip().lower()  # Compare without case
    for h in table.headers:  # Exact name first
        if h.lower() == lowered:  # Same name
            return h  # Found it
    matches = [h for h in table.headers if lowered in h.lower()]  # Columns that contain the name
    if len(matches) == 1:  # Only one fits
        return matches[0]  # Use it
    raise ValueError(  # Explain the problem so the AI can try again
        f"Column '{name}' not found" + (f" (could be: {', '.join(matches)})" if matches else "")  # What went wrong
        + f". Columns in {table.name}: {', '.join(table.headers)}"  # The valid choices
    )  # End of error


def find_table(tables, file, sheet):  # Picks the table the AI asked for
    candidates = [  # Tables whose file (and sheet, if given) match
        t for t in tables  # Every table
        if (not file or file.lower() in t.file.lower()) and (not sheet or (t.sheet or "").lower() == sheet.lower())  # Name matches
    ]  # End of list
    if len(candidates) == 1:  # Exactly one
        return candidates[0]  # Use it
    names = ", ".join(t.name for t in tables) or "none"  # Valid choices
    raise ValueError(f"{'Several' if candidates else 'No'} spreadsheets match. Pick one of: {names}")  # Ask the AI to be specific


def markdown_table(headers, rows):  # Formats rows as a Markdown table
    clean = lambda v: str(v).replace("|", "/").replace("\n", " ")  # Characters that would break the table
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]  # Header and divider
    lines += ["| " + " | ".join(clean(v) for v in row) + " |" for row in rows]  # One line per row
    return "\n".join(lines)  # Hand back the table


@tool(parse_docstring=True)
def query_table(  # The tool the AI calls to look at every row of a spreadsheet
    file: str = "",
    sheet: str = "",
    filters: dict[str, str] | None = None,
    group_by: str = "",
    columns: list[str] | str | None = None,
    limit: int = 30,
) -> str:
    """Filter, list, count and group ALL rows of a spreadsheet (Excel/CSV) in the knowledge base.

    Use this for lists, counts, categories and "which/how many" questions, because it checks every row.

    Args:
        file: Spreadsheet file name. Can be empty if there is only one spreadsheet.
        sheet: Sheet name. Optional.
        filters: Column name -> text the cell must contain (upper/lower case ignored). Use "(blank)" to match empty cells. Every filter must match.
        group_by: Column to group by. Returns how many matching rows have each value of that column.
        columns: Columns to show for each matching row. Default: the first 5 columns.
        limit: Maximum number of rows to show (default 30, max 200).
    """
    try:  # Report problems back to the AI instead of crashing
        table = find_table(load_tables(), file, sheet)  # The spreadsheet to use
        conditions = [(find_column(table, c), str(v).strip().lower()) for c, v in (filters or {}).items()]  # Resolve column names
        matched = [  # Rows that pass every filter
            (n, r) for n, r in table.rows  # Every row
            if all((not r.get(c)) if v == "(blank)" else v in r.get(c, "").lower() for c, v in conditions)  # Each filter
        ]  # End of list
        where = " and ".join(f'{c} contains "{v}"' for c, v in conditions) or "no filters"  # Description of the filters
        header = f"{table.name}: {len(matched)} of {len(table.rows)} rows match ({where})."  # Summary line
        if group_by:  # A category breakdown was asked for
            col = find_column(table, group_by)  # The column to group by
            counts = category_counts(r.get(col) or "(blank)" for _, r in matched)  # Rows per value (spelling differences merged)
            return header + f"\nGrouped by {col}:\n" + markdown_table([col, "Rows"], counts.most_common())  # Value / count table
        if isinstance(columns, str):  # The model sometimes sends "A, B" instead of ["A", "B"]
            columns = [c for c in columns.split(",") if c.strip()]  # Turn it into a list
        shown = [find_column(table, c) for c in columns] if columns else table.headers[:5]  # Columns to show
        shown = list(dict.fromkeys(shown + [c for c, _ in conditions]))  # Always include the filtered columns
        limit = max(1, min(int(limit), MAX_ROWS_SHOWN))  # Keep the limit sensible
        rows = [[n] + [r.get(c, "") for c in shown] for n, r in matched[:limit]]  # The rows to show, with row numbers
        more = f"\n(Showing the first {limit}; {len(matched) - limit} more not shown.)" if len(matched) > limit else ""  # Note if cut off
        return header + "\n" + markdown_table(["Row"] + shown, rows) + more  # Summary + table
    except ValueError as e:  # Wrong file or column name
        return f"Error: {e}"  # Let the AI read it and try again
