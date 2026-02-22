'''
Safe expression evaluator for row-based calculations.

Supports Python-like expressions with row context, using AST validation
for security. Provides fallback to restricted eval for performance.
'''
import ast
import operator
import math
import re
import numpy as np
from typing import Any, Dict, Optional, Union, Callable


class ExpressionEvaluator:
    """
    Safely evaluate Python-like expressions with row context.
    
    Features:
    - AST validation to prevent unsafe operations
    - Support for row["column"] access, arithmetic, comparisons, logical ops
    - Built-in functions: int, float, str, bool, len, round, abs, min, max, sum
    - Conditional expressions (if-else)
    - Safe evaluation with row context
    """
    
    # Allowed AST node types
    ALLOWED_NODES = {
        # Expressions
        ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.BoolOp,
        ast.Name, ast.Constant, ast.Subscript, ast.Index, ast.Slice,
        ast.Tuple, ast.List, ast.Dict, ast.Set,
        # Operators
        ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
        ast.USub, ast.UAdd, ast.Not, ast.Invert,
        ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
        ast.Is, ast.IsNot, ast.In, ast.NotIn,
        ast.And, ast.Or,
        # Function calls
        ast.Call, ast.Attribute,
        # Control flow
        ast.IfExp,
        # Context nodes (safe)
        ast.Load, ast.Store, ast.Del,
    }
    
    # Allowed built-in functions
    ALLOWED_BUILTINS = {
        'int': int,
        'float': float,
        'str': str,
        'bool': bool,
        'len': len,
        'round': round,
        'abs': abs,
        'min': min,
        'max': max,
        'sum': sum,
        'math.sqrt': math.sqrt,
        'math.pow': math.pow,
        'math.exp': math.exp,
        'math.log': math.log,
        'math.sin': math.sin,
        'math.cos': math.cos,
        'math.tan': math.tan,
        'np.where': np.where,
    }
    
    # Allowed attributes (e.g., row.get)
    ALLOWED_ATTRIBUTES = {'get', 'lower', 'upper', 'strip', 'replace', 'split', 'str', 'contains', 'where'}
    
    def __init__(self, expression: str, use_ast_validation: bool = True):
        """
        Initialize evaluator with expression.
        
        Args:
            expression: Python-like expression string
            use_ast_validation: If True, validate AST for security (slower)
        """
        self.expression = expression.strip()
        self.use_ast_validation = use_ast_validation
        self._compiled = None
        
        if use_ast_validation:
            self._validate_expression()
        
    def _validate_expression(self) -> None:
        """
        Validate expression AST for security.
        Raises ValueError if unsafe nodes are found.
        """
        try:
            tree = ast.parse(self.expression, mode='eval')
        except SyntaxError as e:
            raise ValueError(f"Invalid expression syntax: {e}")
        
        for node in ast.walk(tree):
            node_type = type(node)
            if node_type not in self.ALLOWED_NODES:
                raise ValueError(
                    f"Unsafe operation detected: {node_type.__name__} "
                    f"at line {node.lineno if hasattr(node, 'lineno') else '?'}"
                )
            
            # Additional checks for Call nodes
            if isinstance(node, ast.Call):
                # Check function name
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    if func_name not in self.ALLOWED_BUILTINS:
                        # Check if it's a math function
                        if not (func_name.startswith('math.') and func_name in self.ALLOWED_BUILTINS):
                            raise ValueError(f"Disallowed function: {func_name}")
                elif isinstance(node.func, ast.Attribute):
                    # Allow row.get etc.
                    attr_name = node.func.attr
                    if attr_name not in self.ALLOWED_ATTRIBUTES:
                        # Sometimes node.func corresponds to an object's attribute (like pd.Series.str.contains)
                        # Let's be lenient on pandas attribute chains for string manipulation within eval
                        if not attr_name in ['contains', 'str', 'where']:
                            raise ValueError(f"Disallowed attribute: {attr_name}")
    
    def compile(self) -> Callable:
        """
        Compile expression into a callable function.
        Returns a function that takes a row dict and returns evaluated value.
        """
        if self._compiled is not None:
            return self._compiled
        
        # Create safe globals
        safe_globals = {
            '__builtins__': {
                'int': int,
                'float': float,
                'str': str,
                'bool': bool,
                'len': len,
                'round': round,
                'abs': abs,
                'min': min,
                'max': max,
                'sum': sum,
                'math': math,
                'np': np,
            },
            'math': math,
            'np': np,
            'row': None,  # Placeholder, will be replaced with actual row
        }
        
        # Add math functions individually for easier access
        for name, func in self.ALLOWED_BUILTINS.items():
            if name.startswith('math.') or name.startswith('np.'):
                # Will be accessed via math/np module
                continue
            safe_globals[name] = func
        
        try:
            # Compile expression
            code = compile(self.expression, '<string>', 'eval')
            
            def evaluator(row: Dict[str, Any]) -> Any:
                """Evaluate expression with given row context."""
                safe_globals['row'] = row
                try:
                    return eval(code, safe_globals, {})
                except Exception as e:
                    # Provide more context in error
                    raise ValueError(
                        f"Error evaluating expression '{self.expression}': {e}"
                    ) from e
            
            self._compiled = evaluator
            return evaluator
        except SyntaxError as e:
            raise ValueError(f"Expression compilation failed: {e}")
    
    def evaluate(self, row: Dict[str, Any]) -> Any:
        """
        Evaluate expression for a single row.
        
        Args:
            row: Dictionary representing a row of data
            
        Returns:
            Evaluated result
        """
        if self._compiled is None:
            self.compile()
        return self._compiled(row)
    
    @classmethod
    def evaluate_batch(
        cls,
        expression: str,
        rows: list[Dict[str, Any]],
        default: Any = None,
        use_ast_validation: bool = True
    ) -> list[Any]:
        """
        Evaluate expression for multiple rows efficiently.
        
        Args:
            expression: Expression string
            rows: List of row dictionaries
            default: Default value if evaluation fails for a row
            use_ast_validation: Whether to validate AST
            
        Returns:
            List of results, same length as rows
        """
        evaluator = cls(expression, use_ast_validation)
        evaluator.compile()
        
        results = []
        for row in rows:
            try:
                results.append(evaluator.evaluate(row))
            except Exception:
                results.append(default)
        return results


def safe_eval(expression: str, row: Dict[str, Any], default: Any = None) -> Any:
    """
    Convenience function for one-off expression evaluation.
    
    Args:
        expression: Expression string
        row: Row dictionary
        default: Value to return if evaluation fails
        
    Returns:
        Evaluated result or default
    """
    try:
        evaluator = ExpressionEvaluator(expression)
        return evaluator.evaluate(row)
    except Exception:
        return default


def validate_expression(expression: str) -> bool:
    """
    Validate expression syntax and safety.
    
    Args:
        expression: Expression string
        
    Returns:
        True if valid, False otherwise
    """
    try:
        ExpressionEvaluator(expression)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    # Simple test
    test_row = {"age": 25, "salary": 50000, "name": "Alice", "active": True}
    
    # Test basic arithmetic
    expr1 = "row['age'] * 2 + 5"
    evaluator1 = ExpressionEvaluator(expr1)
    print(f"{expr1} = {evaluator1.evaluate(test_row)}")  # Should be 55
    
    # Test conditional
    expr2 = "'Adult' if row['age'] >= 18 else 'Minor'"
    evaluator2 = ExpressionEvaluator(expr2)
    print(f"{expr2} = {evaluator2.evaluate(test_row)}")  # Should be 'Adult'
    
    # Test string concatenation
    expr3 = "row['name'] + ' is ' + str(row['age'])"
    evaluator3 = ExpressionEvaluator(expr3)
    print(f"{expr3} = {evaluator3.evaluate(test_row)}")
    
    # Test batch evaluation
    rows = [
        {"age": 15, "salary": 20000},
        {"age": 30, "salary": 60000},
        {"age": 45, "salary": 80000},
    ]
    results = ExpressionEvaluator.evaluate_batch(
        "row['salary'] * 0.1 if row['age'] > 20 else 0",
        rows
    )
    print(f"Batch results: {results}")
