from tinydb import TinyDB, where
from itertools import islice
from config import DB_PATH
from utils import create_dir_safely


# Ensure the database directory exists before initializing TinyDB
create_dir_safely(DB_PATH.parent)

# Initialize TinyDB and tables
db          = TinyDB(DB_PATH)
users_tbl   = db.table("users")
stats_tbl   = db.table("stats")
organized_tbl = db.table("organized")
error_log_tbl = db.table("error_log")

def load_active_users() -> set[int]:
    """Load active users from TinyDB."""
    return {row['id'] for row in users_tbl.all()}

def save_active_users(users: set[int]):
    """Persist any new users via TinyDB."""
    for uid in users:
        if not users_tbl.contains(where('id') == uid):
            users_tbl.insert({'id': uid})

def paginate_db(table, limit=10, offset=0):
    """Helper: paginate TinyDB results (returns page + total count)"""
    all_entries = sorted(table.all(), key=lambda r: r.get("timestamp", ""), reverse=True)
    total = len(all_entries)
    page = list(islice(all_entries, offset, offset + limit))
    return page, total
