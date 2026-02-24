#!/usr/bin/env python3
"""
Failsafe Pipeline for agent generation.

Provides multi-stage validation with automatic fixes and user intervention.
"""
import os
import re
from typing import Dict, Any, List, Tuple, Optional
from enum import Enum

from .code_validator import CodeValidator
from .enhanced_template_manager import EnhancedTemplateManager


class ValidationStage(Enum):
    SYNTAX = "syntax"
    IMPORTS = "imports"
    TOOL_SIGNATURES = "tool_signatures"
    TEMPLATE_COMPATIBILITY = "template_compatibility"
    RUNTIME_SAFETY = "runtime_safety"


class FixType(Enum):
    INDENTATION = "indentation"
    MISSING_COLON = "missing_colon"
    UNCLOSED_BRACKET = "unclosed_bracket"
    MISSING_IMPORT = "missing_import"
    DISALLOWED_IMPORT = "disallowed_import"
    MISSING_RETURN_TYPE = "missing_return_type"
    MISSING_TOOL_REGISTRY = "missing_tool_registry"


class FailsafePipeline:
    """Multi-stage validation with automatic fixes."""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.validator = CodeValidator()
        self.template_manager = EnhancedTemplateManager()
        self.validation_results = []
        self.automatic_fixes = []
        self.manual_interventions = []
    
    def validate_and_fix(self, code: str, file_type: str) -> Tuple[str, List[Dict]]:
        """Validate code and apply automatic fixes."""
        fixed_code = code
        
        # Stage 1: Syntax validation
        syntax_result = self.validator.validate_python_syntax(fixed_code)
        if syntax_result:
            fixed_code, syntax_fixes = self._apply_syntax_fixes(fixed_code, syntax_result)
            self.automatic_fixes.extend(syntax_fixes)
        
        # Stage 2: Import validation
        import_result = self.validator.validate_imports(fixed_code, file_type)
        if import_result:
            fixed_code, import_fixes = self._apply_import_fixes(fixed_code, import_result)
            self.automatic_fixes.extend(import_fixes)
        
        # Stage 3: Tool signature validation (for tools.py only)
        if file_type == "tools":
            tool_result = self.validator.validate_tool_functions(fixed_code)
            if tool_result:
                fixed_code, tool_fixes = self._apply_tool_fixes(fixed_code, tool_result)
                self.automatic_fixes.extend(tool_fixes)
        
        # Stage 4: Template compatibility
        template_issues = self.validator.validate_file_structure(fixed_code, file_type)
        if template_issues:
            fixed_code, template_fixes = self._apply_template_fixes(fixed_code, template_issues, file_type)
            self.automatic_fixes.extend(template_fixes)
            
            # Some template issues require manual intervention
            manual_issues = [issue for issue in template_issues 
                           if issue.get('severity') == 'error' and 
                           not self._can_auto_fix(issue)]
            self.manual_interventions.extend(manual_issues)
        
        return fixed_code, self.manual_interventions
    
    def _apply_syntax_fixes(self, code: str, issues: List[Dict]) -> Tuple[str, List[Dict]]:
        """Apply automatic syntax fixes."""
        fixed_code = code
        applied_fixes = []
        
        for issue in issues:
            if issue['severity'] != 'error':
                continue
                
            message = issue['message'].lower()
            line = issue['line']
            
            # Try to fix common syntax errors
            if 'indentation' in message:
                # Simple indentation fix - add 4 spaces
                lines = fixed_code.split('\n')
                if line <= len(lines):
                    original = lines[line-1]
                    # Count leading spaces
                    leading_spaces = len(original) - len(original.lstrip())
                    if leading_spaces % 4 != 0:
                        # Fix to multiple of 4
                        new_spaces = ((leading_spaces // 4) + 1) * 4
                        lines[line-1] = ' ' * new_spaces + original.lstrip()
                        fixed_code = '\n'.join(lines)
                        applied_fixes.append({
                            'type': FixType.INDENTATION.value,
                            'line': line,
                            'description': 'Fixed indentation'
                        })
            
            elif 'missing colon' in message:
                # Add missing colon at end of line
                lines = fixed_code.split('\n')
                if line <= len(lines):
                    if not lines[line-1].strip().endswith(':'):
                        lines[line-1] = lines[line-1].rstrip() + ':'
                        fixed_code = '\n'.join(lines)
                        applied_fixes.append({
                            'type': FixType.MISSING_COLON.value,
                            'line': line,
                            'description': 'Added missing colon'
                        })
        
        return fixed_code, applied_fixes
    
    def _apply_import_fixes(self, code: str, issues: List[Dict]) -> Tuple[str, List[Dict]]:
        """Apply automatic import fixes."""
        fixed_code = code
        applied_fixes = []
        
        for issue in issues:
            if 'disallowed import' in issue['message'].lower():
                # Try to replace disallowed imports with allowed ones
                match = re.search(r'Disallowed import:?\s*([\w.]+)', issue['message'])
                if match:
                    disallowed = match.group(1)
                    # Check if it's a common import we can replace
                    replacements = {
                        'numpy': 'math',
                        'pandas': 'csv',
                        'requests': 'urllib.request',
                        'beautifulsoup4': 'html.parser'
                    }
                    
                    if disallowed in replacements:
                        replacement = replacements[disallowed]
                        fixed_code = fixed_code.replace(
                            f'import {disallowed}',
                            f'import {replacement}'
                        )
                        fixed_code = fixed_code.replace(
                            f'from {disallowed} import',
                            f'from {replacement} import'
                        )
                        applied_fixes.append({
                            'type': FixType.DISALLOWED_IMPORT.value,
                            'line': issue['line'],
                            'description': f'Replaced {disallowed} with {replacement}'
                        })
            
            elif 'missing import' in issue['message'].lower():
                # Add missing import
                match = re.search(r'Missing import:?\s*([\w.]+)', issue['message'])
                if match:
                    missing_import = match.group(1)
                    # Add import at the top
                    import_line = f'import {missing_import}\n'
                    if 'import ' in fixed_code:
                        # Insert after first import
                        lines = fixed_code.split('\n')
                        for i, line in enumerate(lines):
                            if line.strip().startswith('import '):
                                lines.insert(i + 1, f'import {missing_import}')
                                break
                        fixed_code = '\n'.join(lines)
                    else:
                        fixed_code = import_line + fixed_code
                    
                    applied_fixes.append({
                        'type': FixType.MISSING_IMPORT.value,
                        'line': issue['line'],
                        'description': f'Added import {missing_import}'
                    })
        
        return fixed_code, applied_fixes
    
    def _apply_tool_fixes(self, code: str, issues: List[Dict]) -> Tuple[str, List[Dict]]:
        """Apply automatic tool function fixes."""
        fixed_code = code
        applied_fixes = []
        
        for issue in issues:
            if 'should return Dict[str, Any]' in issue['message']:
                # Add return type annotation
                match = re.search(r'function (\w+)', issue['message'])
                if match:
                    func_name = match.group(1)
                    # Find the function definition
                    lines = fixed_code.split('\n')
                    for i, line in enumerate(lines):
                        if f'def {func_name}(' in line and '->' not in line:
                            # Add return type
                            lines[i] = line.rstrip() + ' -> Dict[str, Any]'
                            fixed_code = '\n'.join(lines)
                            applied_fixes.append({
                                'type': FixType.MISSING_RETURN_TYPE.value,
                                'line': i + 1,
                                'description': f'Added return type to {func_name}'
                            })
                            break
            
            elif 'Missing TOOL_REGISTRY' in issue['message']:
                # Add basic TOOL_REGISTRY
                tool_registry = '''
# Tool registry
TOOL_REGISTRY = {
    # Add your tools here
    # "example_tool": {
    #     "function": example_tool,
    #     "description": "Example tool",
    #     "input_schema": {
    #         "type": "object",
    #         "properties": {
    #             "param1": {"type": "string", "description": "Parameter"}
    #         },
    #         "required": ["param1"]
    #     }
    # }
}
'''
                fixed_code = fixed_code.rstrip() + '\n' + tool_registry
                applied_fixes.append({
                    'type': FixType.MISSING_TOOL_REGISTRY.value,
                    'line': len(fixed_code.split('\n')) - len(tool_registry.split('\n')) + 1,
                    'description': 'Added TOOL_REGISTRY template'
                })
        
        return fixed_code, applied_fixes
    
    def _apply_template_fixes(self, code: str, issues: List[Dict], file_type: str) -> Tuple[str, List[Dict]]:
        """Apply template compatibility fixes."""
        fixed_code = code
        applied_fixes = []
        
        for issue in issues:
            if 'Missing shared.primitives import' in issue['message'] and file_type == 'tools':
                # Add shared.primitives import
                import_section = '''import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from shared.primitives import (
    Text, Button, Card, Table, List_, Alert, ProgressBar, MetricCard,
    CodeBlock, Image, Grid, Tabs, Divider, Input, BarChart, LineChart,
    PieChart, PlotlyChart, Collapsible, Container,
    create_ui_response
)
from typing import Dict, Any, List, Optional

'''
                # Check if there are already imports
                if 'import ' in fixed_code:
                    # Insert at the beginning
                    fixed_code = import_section + fixed_code
                else:
                    fixed_code = import_section + fixed_code
                
                applied_fixes.append({
                    'type': FixType.MISSING_IMPORT.value,
                    'line': 1,
                    'description': 'Added shared.primitives import'
                })
        
        return fixed_code, applied_fixes
    
    def _can_auto_fix(self, issue: Dict) -> bool:
        """Check if an issue can be fixed automatically."""
        message = issue['message'].lower()
        
        auto_fixable_patterns = [
            'indentation',
            'missing colon',
            'missing import',
            'disallowed import',
            'should return dict',
            'missing tool_registry',
            'missing shared.primitives import'
        ]
        
        return any(pattern in message for pattern in auto_fixable_patterns)
    
    def generate_fallback_templates(self, session: Dict[str, Any], 
                                   tool_descriptions: List[Dict] = None) -> Dict[str, str]:
        """Generate fallback templates when LLM generation fails."""
        agent_name = session.get("name", "custom").replace(" ", "_").lower()
        
        return self.template_manager.generate_all_templates(
            agent_name, session, tool_descriptions
        )
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """Get summary of validation results."""
        return {
            'automatic_fixes_applied': len(self.automatic_fixes),
            'manual_interventions_needed': len(self.manual_interventions),
            'automatic_fixes': self.automatic_fixes,
            'manual_interventions': self.manual_interventions,
            'is_fixable': len(self.manual_interventions) == 0
        }



if __name__ == "__main__":
    # Test the failsafe pipeline
    test_code = """
def example_tool(param1):
    return {"result": param1}
"""
    
    pipeline = FailsafePipeline("test_agent")
    fixed_code, interventions = pipeline.validate_and_fix(test_code, "tools")
    
    print("Original code:")
    print(test_code)
    print("\nFixed code:")
    print(fixed_code)
    print("\nAutomatic fixes applied:")
    for fix in pipeline.automatic_fixes:
        print(f"  - {fix['description']} (line {fix['line']})")
    
    if interventions:
        print("\nManual interventions needed:")
        for intervention in interventions:
            print(f"  - {intervention['message']}")
    else:
        print("\nNo manual interventions needed!")
