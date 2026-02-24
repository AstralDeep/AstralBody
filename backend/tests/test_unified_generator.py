#!/usr/bin/env python3
"""Test the unified agent generator."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath('.'))

from orchestrator.unified_agent_generator import UnifiedAgentGeneratorClient

async def test_basic():
    """Test basic functionality of the unified generator."""
    print("Testing UnifiedAgentGeneratorClient...")
    
    # Create instance
    generator = UnifiedAgentGeneratorClient()
    
    # Test 1: Check if LLM is available
    print(f"LLM available: {generator.llm_available}")
    
    # Test 2: Create a mock session
    print("\nTesting session management...")
    
    # We can't actually start a session without proper auth, but we can test the structure
    try:
        # Test template generation
        from orchestrator.enhanced_template_manager import EnhancedTemplateManager
        template_manager = EnhancedTemplateManager()
        
        test_session = {
            "name": "TestAgent",
            "persona": "A test agent for validation",
            "tools_desc": "Fetches data and analyzes it",
            "messages": []
        }
        
        templates = template_manager.generate_all_templates(
            "test_agent", 
            test_session,
            [{"name": "fetch_data", "description": "Fetch data from API"}]
        )
        
        print(f"Generated {len(templates)} templates: {list(templates.keys())}")
        
        # Test validation
        from orchestrator.code_validator import CodeValidator
        validator = CodeValidator()
        
        for file_type, content in templates.items():
            result = validator.validate_all(content, file_type)
            print(f"  {file_type}: valid={result['valid']}, errors={result['error_count']}, warnings={result['warning_count']}")
        
        print("\nAll basic tests passed!")
        return True
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        success = asyncio.run(test_basic())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\nTest interrupted")
        sys.exit(1)