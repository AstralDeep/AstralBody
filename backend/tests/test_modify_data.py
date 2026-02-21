import os
import sys
import json
import csv
import io

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.general.mcp_tools import modify_data

def test_modify_data_with_file():
    # Create a temporary source file
    src_file = "src_test.csv"
    with open(src_file, 'w') as f:
        f.write("Code,Title\nA00,Cholera\nA01,Typhoid\nA02,Vibrio")
    
    abs_src_path = os.path.abspath(src_file)
    
    modifications = [
        {"action": "add_column", "name": "processed", "value": "true"}
    ]
    
    print(f"Testing modify_data with file_path: {abs_src_path}...")
    result = modify_data(file_path=abs_src_path, modifications=modifications, filename="file_modified.csv")
    
    # Check if file exists
    file_path = result["_data"]["file_path"]
    if os.path.exists(file_path):
        print(f"Success: File created at {file_path}")
        with open(file_path, 'r') as f:
            content = f.read()
            print("File Content:")
            print(content)
            if "true" in content and "processed" in content and "Vibrio" in content:
                print("Verification PASSED: Column, values, and all rows found.")
            else:
                print("Verification FAILED: Content mismatch.")
    else:
        print(f"Failure: File not found at {file_path}")
    
    # Cleanup
    if os.path.exists(src_file):
        os.remove(src_file)

if __name__ == "__main__":
    # test_modify_data() # Keep previous test if needed or just run the new one
    test_modify_data_with_file()
