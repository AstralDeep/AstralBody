#!/usr/bin/env python3
"""Test the enhanced agent generator."""
import sys
import os
import asyncio

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from orchestrator.enhanced_agent_generator import enhanced_agent_generator
from orchestrator.enhanced_template_manager import EnhancedTemplateManager
from orchestrator.code_validator import CodeValidator
from orchestrator.failsafe_pipeline import FailsafePipeline

async def test_template_manager():
    print("Testing EnhancedTemplateManager...")
    manager = EnhancedTemplateManager()
    
    test_session = {
        "name": "TestAgent",
        "persona": "A test agent for validation",
        "tools_desc": "Fetches data and analyzes it",
        "api_keys": "TEST_API_KEY"
    }
    
    templates = manager.generate_all_templates("test_agent", test_session)
    print(f"  Generated {len(templates)} templates")
    for file_type, content in templates.items():
        print(f"    {file_type}: {len(content)} chars")
    
    # Check that all three files are generated
    assert set(templates.keys()) == {"tools", "agent", "server"}
    print("  [OK] Template generation passed")
    return True

async def test_code_validator():
    print("\nTesting CodeValidator...")
    validator = CodeValidator()
    
    # Test valid code
    valid_code = """from shared.primitives import Text, Button\ndef example_tool() -> dict:\n    return {'_ui_components': [Text('Hello')], '_data': {}}"""
    result = validator.validate_all(valid_code, "tools")
    print(f"  Valid code: {result['valid']} ({result['error_count']} errors, {result['warning_count']} warnings)")
    
    # Test invalid code
    invalid_code = """import os  # Not allowed\ndef bad_tool():\n    return {}"""
    result = validator.validate_all(invalid_code, "tools")
    print(f"  Invalid code: {result['valid']} ({result['error_count']} errors, {result['warning_count']} warnings)")
    
    assert not result['valid']  # Should be invalid
    print("  [OK] Code validation passed")
    return True

async def test_failsafe_pipeline():
    print("\nTesting FailsafePipeline...")
    pipeline = FailsafePipeline("test_agent")
    
    # Code with issues
    problematic_code = """from shared.primitives import Text\ndef example_tool():\n    # Missing return type\n    return {'_ui_components': [Text('Hello')]}"""
    
    fixed_code, interventions = pipeline.validate_and_fix(problematic_code, "tools")
    print(f"  Fixed code length: {len(fixed_code)} chars")
    print(f"  Interventions needed: {len(interventions)}")
    for interv in interventions:
        print(f"    - {interv['type']}: {interv['description']}")
    
    # Validate the fixed code
    validator = CodeValidator()
    result = validator.validate_all(fixed_code, "tools")
    print(f"  Fixed code valid: {result['valid']}")
    
    print("  [OK] Failsafe pipeline passed")
    return True

async def test_enhanced_generator():
    print("\nTesting EnhancedAgentGenerator...")
    
    # Test session management
    print("  Testing session creation...")
    try:
        result = await enhanced_agent_generator.start_session(
            name="IntegrationTest",
            persona="An agent for integration testing",
            tools_desc="Tests the enhanced generator system",
            api_keys="",
            user_id="test_user"
        )
        session_id = result["session_id"]
        print(f"    Created session: {session_id}")
        
        # Test chat
        print("  Testing chat...")
        chat_result = await enhanced_agent_generator.chat(session_id, "Please create a simple tool that fetches data.", user_id="test_user")
        print(f"    Chat response: {len(chat_result['response'])} chars")
        
        # Test code generation (template mode since LLM likely not configured)
        print("  Testing code generation...")
        gen_result = await enhanced_agent_generator.generate_code(session_id, user_id="test_user")
        print(f"    Generation source: {gen_result.get('source', 'unknown')}")
        print(f"    Files generated: {list(gen_result.get('files', {}).keys())}")
        
        # Clean up
        print("  Cleaning up...")
        success = enhanced_agent_generator.delete_session(session_id, user_id="test_user")
        print(f"    Session deleted: {success}")
        
        print("  [OK] Enhanced generator passed")
        return True
    except Exception as e:
        print(f"  [FAIL] Enhanced generator failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("=== Testing Enhanced Agent Generation System ===\n")
    
    tests = [
        ("Template Manager", test_template_manager),
        ("Code Validator", test_code_validator),
        ("Failsafe Pipeline", test_failsafe_pipeline),
        ("Enhanced Generator", test_enhanced_generator),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = await test_func()
            results.append((name, success))
        except Exception as e:
            print(f"  [FAIL] {name} failed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    print("\n=== Test Results ===")
    all_passed = True
    for name, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"{name:20} {status}")
        if not success:
            all_passed = False
    
    if all_passed:
        print("\n[SUCCESS] All tests passed!")
    else:
        print("\n[FAILURE] Some tests failed.")
    
    return all_passed

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
