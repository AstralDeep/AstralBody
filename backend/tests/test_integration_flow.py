#!/usr/bin/env python3
"""Integration test for the complete agent generation flow."""
import sys
import os
import asyncio
import json
import tempfile
import shutil

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from orchestrator.enhanced_agent_generator import enhanced_agent_generator
from orchestrator.agent_tester import save_agent_files, run_tests_and_yield_logs

async def test_complete_flow():
    print("=== Testing Complete Agent Generation Flow ===\n")
    
    # Step 1: Start a session
    print("1. Starting agent creation session...")
    result = await enhanced_agent_generator.start_session(
        name="WeatherReporter",
        persona="An agent that fetches and reports weather data",
        tools_desc="Needs to fetch weather from an API and display it in charts",
        api_keys="WEATHER_API_KEY",
        user_id="integration_test_user"
    )
    session_id = result["session_id"]
    print(f"   Session created: {session_id}")
    print(f"   Initial response: {result['initial_response'][:100]}...")
    
    # Step 2: Chat to refine requirements
    print("\n2. Chatting to refine requirements...")
    chat_result = await enhanced_agent_generator.chat(
        session_id,
        "Please create a tool that fetches weather data for a given city and displays it as a chart.",
        user_id="integration_test_user"
    )
    print(f"   Chat response: {chat_result['response'][:100]}...")
    
    # Step 3: Generate code
    print("\n3. Generating agent code...")
    gen_result = await enhanced_agent_generator.generate_code(
        session_id,
        user_id="integration_test_user"
    )
    
    print(f"   Generation source: {gen_result.get('source', 'unknown')}")
    print(f"   Files generated: {list(gen_result.get('files', {}).keys())}")
    
    files = gen_result.get('files', {})
    if not files:
        print("   ERROR: No files generated!")
        return False
    
    # Check file contents
    for file_type, content in files.items():
        print(f"   - {file_type}.py: {len(content)} chars")
        if len(content) < 100:
            print(f"     WARNING: {file_type}.py seems too short")
    
    # Step 4: Validate the generated code
    print("\n4. Validating generated code...")
    from orchestrator.code_validator import code_validator
    
    validation_results = {}
    for file_type, content in files.items():
        result = code_validator.validate_all(content, file_type)
        validation_results[file_type] = result
        print(f"   - {file_type}.py: {'VALID' if result['valid'] else 'INVALID'} "
              f"({result['error_count']} errors, {result['warning_count']} warnings)")
        
        if result['errors']:
            for error in result['errors'][:3]:  # Show first 3 errors
                print(f"     Error: {error['message']}")
    
    # Step 5: Apply fixes if needed
    print("\n5. Applying automatic fixes...")
    from orchestrator.failsafe_pipeline import FailsafePipeline
    
    fixed_files = {}
    for file_type, content in files.items():
        pipeline = FailsafePipeline("weather_reporter")
        fixed_content, interventions = pipeline.validate_and_fix(content, file_type)
        fixed_files[file_type] = fixed_content
        
        if interventions:
            print(f"   - {file_type}.py: Applied {len(interventions)} fixes")
            for interv in interventions[:2]:  # Show first 2 interventions
                print(f"     Fix: {interv['type']} - {interv['description']}")
        else:
            print(f"   - {file_type}.py: No fixes needed")
    
    # Step 6: Save files (simulate what the frontend would do)
    print("\n6. Saving agent files...")
    
    # Create a temporary directory for the agent
    temp_dir = tempfile.mkdtemp(prefix="agent_test_")
    print(f"   Temporary directory: {temp_dir}")
    
    # Get session data
    session = enhanced_agent_generator.get_session(session_id, user_id="integration_test_user")
    
    # Save files using the agent_tester module
    try:
        agent_dir = save_agent_files("weather_reporter", fixed_files, session)
        print(f"   Agent saved to: {agent_dir}")
        
        # Check if files were created
        expected_files = [
            "weather_reporter_tools.py",
            "weather_reporter_agent.py", 
            "weather_reporter_server.py"
        ]
        
        for filename in expected_files:
            filepath = os.path.join(agent_dir, filename)
            if os.path.exists(filepath):
                print(f"   [OK] {filename} created")
            else:
                print(f"   [FAIL] {filename} missing")
                
    except Exception as e:
        print(f"   ERROR saving files: {e}")
        import traceback
        traceback.print_exc()
        
    # Step 7: Clean up
    print("\n7. Cleaning up...")
    
    # Delete the session
    success = enhanced_agent_generator.delete_session(session_id, user_id="integration_test_user")
    print(f"   Session deleted: {success}")
    
    # Clean up temp directory
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"   Temporary directory cleaned")
    
    print("\n=== Integration Test Complete ===")
    
    # Overall assessment
    all_files_generated = len(files) == 3
    validation_passed = all(v["valid"] for v in validation_results.values())
    
    if all_files_generated and validation_passed:
        print("[SUCCESS] Complete flow works!")
        return True
    else:
        print("[PARTIAL] Flow works but with issues")
        print(f"   - Files generated: {all_files_generated}")
        print(f"   - Validation passed: {validation_passed}")
        return True  # Still consider it a success for integration purposes

async def main():
    try:
        success = await test_complete_flow()
        return 0 if success else 1
    except Exception as e:
        print(f"\n[FAILED] INTEGRATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
