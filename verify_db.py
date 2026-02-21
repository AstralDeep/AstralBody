import sys
import os
import sqlite3

# Ensure backend is in path
sys.path.insert(0, os.path.abspath('backend'))

from shared.database import Database

db_path = 'backend/data/chats.db'
db = Database(db_path)

print("Checking table_info for chat_files...")
try:
    cols = db.fetch_all("PRAGMA table_info(chat_files)")
    for col in cols:
        print(f"Column: {col['name']} ({col['type']})")
    
    if len(cols) == 0:
        print("Table chat_files NOT FOUND!")
    else:
        print("Table chat_files verified.")
except Exception as e:
    print(f"Error: {e}")
