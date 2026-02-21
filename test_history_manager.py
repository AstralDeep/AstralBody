import sys
import os
import uuid

# Ensure backend is in path
sys.path.insert(0, os.path.abspath('backend'))

from orchestrator.history import HistoryManager

# Initialize HistoryManager (it uses backend/data/chats.db by default)
# We'll use a unique chat ID to avoid conflicts
history = HistoryManager('backend/data')

chat_id = history.create_chat()
print(f"Created test chat: {chat_id}")

original = "test_data_verification.csv"
backend = "y:\\WORK\\MCP\\AstralBody\\backend\\tmp_uploads\\test-uuid.csv"

print(f"Adding mapping: {original} -> {backend}")
history.add_file_mapping(chat_id, original, backend)

print("Retrieving mappings...")
mappings = history.get_file_mappings(chat_id)
print(f"Mappings found: {mappings}")

success = False
for m in mappings:
    if m['original_name'] == original and m['backend_path'] == backend:
        success = True
        break

if success:
    print("SUCCESS: File mapping persistence working!")
else:
    print("FAILURE: File mapping persistence failed!")
