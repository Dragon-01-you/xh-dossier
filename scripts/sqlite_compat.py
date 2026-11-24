"""SQLite connection helper.

On some Windows accounts the default DELETE journal mode can create a
``-journal`` file but fail to commit; callers then see ``no such table`` even
though CREATE TABLE returned successfully. TRUNCATE/PERSIST keep the journal
file in place and work in that environment. This helper is intentionally tiny
so every pipeline script can use it without extra dependencies.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union


def connect_db(path: Union[str, Path]) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    try:
        con.execute("PRAGMA journal_mode=TRUNCATE")
    except sqlite3.DatabaseError:
        # Read-only databases and in-memory DBs are fine with the default.
        pass
    return con
