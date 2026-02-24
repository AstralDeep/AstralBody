#!/usr/bin/env python3
"""
Code Validator for agent generation.

Validates Python code for syntax, imports, and tool function compliance.
"""
import ast
import re
from typing import Dict, Any, List, Tuple, Optional


class CodeValidator:
    """Validate generated Python code for agent files."""
    
    # Allowed imports for tools.py
    ALLOWED_IMPORTS = {
        'shared.primitives': [
            'Text', 'Button', 'Card', 'Table', 'List_', 'Alert',
            'ProgressBar', 'MetricCard', 'CodeBlock', 'Image', 'Grid',
            'Tabs', 'Divider', 'Input', 'BarChart', 'LineChart',
            'PieChart', 'PlotlyChart', 'Collapsible', 'Container',
            'create_ui_response'
        ],
        'typing': ['Dict', 'Any', 'List', 'Optional', 'Union'],
        'os': ['*'],
        'sys': ['*'],
        'json': ['*'],
        'datetime': ['*'],
        'time': ['*'],
        'asyncio': ['*'],
        'logging': ['*']
    }
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def validate_python_syntax(self, code: str) -> List[Dict[str, Any]]:
        """Validate Python syntax using ast."""
        issues = []
        try:
            ast.parse(code)
        except SyntaxError as e:
            issues.append({
                'line': e.lineno,
                'column': e.offset or 0,
                'message': f'Syntax error: {e.msg}',
                'severity': 'error',
                'fix_suggestion': 'Check Python syntax and indentation'
            })
        except Exception as e:
            issues.append({
                'line': 1,
                'column': 1,
                'message': f'Error parsing code: {str(e)}',
                'severity': 'error'
            })
        
        return issues
    
    def validate_imports(self, code: str, file_type: str) -> List[Dict[str, Any]]:
        """Validate that only allowed imports are used."""
        issues = []
        
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # If we can't parse, skip import validation
            return issues
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name
                    if module_name not in self.ALLOWED_IMPORTS:
                        issues.append({
                            'line': node.lineno,
                            'column': node.col_offset,
                            'message': f'Disallowed import: {module_name}',
                            'severity': 'error',
                            'fix_suggestion': f'Use allowed imports from: {list(self.ALLOWED_IMPORTS.keys())}'
                        })
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ''
                if module_name not in self.ALLOWED_IMPORTS:
                    issues.append({
                        'line': node.lineno,
                        'column': node.col_offset,
                        'message': f'Disallowed import from: {module_name}',
                        'severity': 'error'
                    })
                else:
                    # Check specific imports
                    allowed = self.ALLOWED_IMPORTS[module_name]
                    for alias in node.names:
                        import_name = alias.name
                        if allowed != ['*'] and import_name not in allowed:
                            issues.append({
                                'line': node.lineno,
                                'column': node.col_offset,
                                'message': f'Disallowed import: {import_name} from {module_name}',
                                'severity': 'error',
                                'fix_suggestion': f'Allowed imports from {module_name}: {allowed}'
                            })
        
        return issues
    
    def validate_tool_functions(self, code: str) -> List[Dict[str, Any]]:
        """Validate tool function signatures and TOOL_REGISTRY."""
        issues = []
        
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # If we can't parse, skip tool validation
            return issues
        
        # Find all function definitions
        functions = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions[node.name] = node
        
        # Find TOOL_REGISTRY
        tool_registry = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == 'TOOL_REGISTRY':
                        tool_registry = node
                        break
        
        if not tool_registry:
            issues.append({
                'line': 1,
                'column': 1,
                'message': 'Missing TOOL_REGISTRY definition',
                'severity': 'error',
                'fix_suggestion': 'Define TOOL_REGISTRY = {...} at the bottom of the file'
            })
            return issues
        
        if not isinstance(tool_registry.value, ast.Dict):
            issues.append({
                'line': tool_registry.lineno,
                'column': tool_registry.col_offset,
                'message': 'TOOL_REGISTRY must be a dictionary',
                'severity': 'error'
            })
            return issues
        
        # Validate each tool in registry
        for key, value in zip(tool_registry.value.keys, tool_registry.value.values):
            if isinstance(key, ast.Constant):
                tool_name = key.value
                
                # Check if function exists
                if tool_name not in functions:
                    issues.append({
                        'line': value.lineno if hasattr(value, 'lineno') else tool_registry.lineno,
                        'column': value.col_offset if hasattr(value, 'col_offset') else tool_registry.col_offset,
                        'message': f'Tool {tool_name} registered but function not found',
                        'severity': 'error',
                        'fix_suggestion': f'Define function def {tool_name}(...):'
                    })
                    continue
                
                # Validate function signature
                func_node = functions[tool_name]
                if not self._validate_function_signature(func_node):
                    issues.append({
                        'line': func_node.lineno,
                        'column': func_node.col_offset,
                        'message': f'Tool function {tool_name} should return Dict[str, Any]',
                        'severity': 'warning',
                        'fix_suggestion': 'Add return type annotation: -> Dict[str, Any]'
                    })
        
        return issues
    
    def _validate_function_signature(self, func_node: ast.FunctionDef) -> bool:
        """Validate that function has proper return type annotation."""
        if not func_node.returns:
            return False
        
        # Try to get return type as string
        try:
            returns_str = ast.unparse(func_node.returns)
            return 'Dict' in returns_str or 'dict' in returns_str.lower()
        except:
            return False
    
    def validate_file_structure(self, code: str, file_type: str) -> List[Dict[str, Any]]:
        """Validate file-specific structure requirements."""
        issues = []
        
        if file_type == 'tools':
            # Check for required components
            if 'TOOL_REGISTRY' not in code:
                issues.append({
                    'line': 1,
                    'column': 1,
                    'message': 'Missing TOOL_REGISTRY',
                    'severity': 'error'
                })
            
            if 'from shared.primitives import' not in code:
                issues.append({
                    'line': 1,
                    'column': 1,
                    'message': 'Missing shared.primitives import',
                    'severity': 'error'
                })
            
            # Check for create_ui_response usage
            if 'create_ui_response' not in code and 'create_ui_response' not in self._extract_imports(code):
                issues.append({
                    'line': 1,
                    'column': 1,
                    'message': 'create_ui_response not imported or used',
                    'severity': 'warning',
                    'fix_suggestion': 'Import create_ui_response from shared.primitives'
                })
        
        elif file_type == 'agent':
            # Check for class definition
            if 'class ' not in code:
                issues.append({
                    'line': 1,
                    'column': 1,
                    'message': 'Missing class definition',
                    'severity': 'error'
                })
            
            # Check for agent_id assignment
            if 'self.agent_id =' not in code:
                issues.append({
                    'line': 1,
                    'column': 1,
                    'message': 'Missing self.agent_id assignment',
                    'severity': 'warning'
                })
        
        elif file_type == 'server':
            # Check for class definition
            if 'class ' not in code:
                issues.append({
                    'line': 1,
                    'column': 1,
                    'message': 'Missing class definition',
                    'severity': 'error'
                })
            
            # Check for TOOL_REGISTRY import
            if 'TOOL_REGISTRY' not in code and 'from .*_tools import TOOL_REGISTRY' not in code:
                issues.append({
                    'line': 1,
                    'column': 1,
                    'message': 'Missing TOOL_REGISTRY import',
                    'severity': 'error'
                })
        
        return issues
    
    def _extract_imports(self, code: str) -> List[str]:
        """Extract imported names from code."""
        imports = []
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        imports.append(alias.name)
        except:
            pass
        return imports
    
    def validate_all(self, code: str, file_type: str) -> Dict[str, Any]:
        """Run all validations on the code."""
        self.errors = []
        self.warnings = []
        
        # Run all validations
        syntax_issues = self.validate_python_syntax(code)
        import_issues = self.validate_imports(code, file_type)
        structure_issues = self.validate_file_structure(code, file_type)
        
        if file_type == 'tools':
            tool_issues = self.validate_tool_functions(code)
            all_issues = syntax_issues + import_issues + tool_issues + structure_issues
        else:
            all_issues = syntax_issues + import_issues + structure_issues
        
        # Categorize issues
        for issue in all_issues:
            if issue['severity'] == 'error':
                self.errors.append(issue)
            else:
                self.warnings.append(issue)
        
        return {
            'valid': len(self.errors) == 0,
            'errors': self.errors,
            'warnings': self.warnings,
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
            'summary': f'Found {len(self.errors)} errors and {len(self.warnings)} warnings'
        }


# Singleton instance
code_validator = CodeValidator()


if __name__ == "__main__":
    # Test the validator
    test_code = '''
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.primitives import Text, create_ui_response
from typing import Dict, Any

def example_tool(param1: str) -> Dict[str, Any]:
    """Example tool"""
    return create_ui_response([
        Text(content=f"Result: {param1}", variant="body")
    ])

TOOL_REGISTRY = {
    "example_tool": {
        "function": example_tool,
        "description": "Example tool",
        "input_schema": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "Parameter"}
            },
            "required": ["param1"]
        }
    }
}
'''
    
    validator = CodeValidator()
    result = validator.validate_all(test_code, 'tools')
    
    print(f"Validation result: {result['valid']}")
    print(f"Summary: {result['summary']}")
    
    if result['errors']:
        print("\nErrors:")
        for error in result['errors']:
            print(f"  Line {error['line']}: {error['message']}")
    
    if result['warnings']:
        print("\nWarnings:")
        for warning in result['warnings']:
            print(f"  Line {warning['line']}: {warning['message']}")
