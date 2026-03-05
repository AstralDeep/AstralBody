"""
Agent Spec Validator — validates generated mcp_tools.py against the agent constitution.

Checks: imports, TOOL_REGISTRY structure, tool execution with sample inputs,
return format (_ui_components + _data), and component structure validation.
"""
import ast
import importlib.util
import logging
import os
import sys
import traceback
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, Optional, List

from orchestrator.agent_spec import VALID_COMPONENT_TYPES, PRIMITIVES_SPEC

logger = logging.getLogger("AgentValidator")

# Exceptions that indicate structural code bugs (not transient failures)
STRUCTURAL_EXCEPTIONS = (
    TypeError, NameError, AttributeError, KeyError, ImportError,
    ModuleNotFoundError, SyntaxError, IndentationError, UnboundLocalError,
)

# Exceptions that indicate network/external API failures (transient)
NETWORK_EXCEPTIONS = (ConnectionError, TimeoutError, OSError)

try:
    import requests
    NETWORK_EXCEPTIONS = NETWORK_EXCEPTIONS + (
        requests.exceptions.RequestException,
    )
except ImportError:
    pass

try:
    import httpx
    NETWORK_EXCEPTIONS = NETWORK_EXCEPTIONS + (
        httpx.HTTPError,
    )
except ImportError:
    pass


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationFinding:
    severity: str  # ValidationSeverity value
    category: str  # IMPORT, REGISTRY, EXECUTION, RETURN_FORMAT, COMPONENT
    message: str
    tool_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationReport:
    passed: bool = True
    findings: List[ValidationFinding] = field(default_factory=list)
    tools_tested: int = 0
    tools_passed: int = 0
    tools: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, severity: str, category: str, message: str,
            tool_name: str = None):
        self.findings.append(ValidationFinding(
            severity=severity, category=category,
            message=message, tool_name=tool_name,
        ))
        if severity == ValidationSeverity.ERROR:
            self.passed = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "tools_tested": self.tools_tested,
            "tools_passed": self.tools_passed,
            "findings": [f.to_dict() for f in self.findings],
            "tools": self.tools,
        }


class AgentSpecValidator:
    """Validates generated mcp_tools.py files against the agent constitution."""

    def validate(self, code: str, slug: str, agents_dir: str) -> ValidationReport:
        """Run the full validation pipeline on generated tool code.

        Args:
            code: The mcp_tools.py source code
            slug: The agent slug (directory name)
            agents_dir: Path to backend/agents/

        Returns:
            ValidationReport with findings
        """
        report = ValidationReport()

        # Step 1: Check imports
        self._validate_imports(code, report)

        # Step 2-3: Load and validate TOOL_REGISTRY
        registry = self._load_registry(code, slug, agents_dir, report)
        if registry is None:
            return report

        # Capture tool metadata for the report
        for tool_name, tool_info in registry.items():
            schema = tool_info.get("input_schema", {})
            props = schema.get("properties", {})
            required = schema.get("required", [])
            params = []
            for pname, pinfo in props.items():
                if isinstance(pinfo, dict):
                    params.append({
                        "name": pname,
                        "type": pinfo.get("type", "any"),
                        "description": pinfo.get("description", ""),
                        "required": pname in required,
                    })
            report.tools.append({
                "name": tool_name,
                "description": tool_info.get("description", ""),
                "scope": tool_info.get("scope", "tools:read"),
                "parameters": params,
            })

        # Step 4-7: Validate each tool
        for tool_name, tool_info in registry.items():
            self._validate_tool(tool_name, tool_info, report)

        return report

    def _validate_imports(self, code: str, report: ValidationReport):
        """Check that code imports from shared.primitives."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            report.add(ValidationSeverity.ERROR, "IMPORT",
                       f"Syntax error prevents parsing: {e}")
            return

        has_primitives_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if "shared.primitives" in module or "primitives" in module:
                    has_primitives_import = True
                    break

        if not has_primitives_import:
            report.add(ValidationSeverity.WARNING, "IMPORT",
                       "Code does not import from shared.primitives. "
                       "Tools should use primitive classes (Card, MetricCard, etc.) "
                       "and call .to_json() instead of constructing raw dicts.")

    def _load_registry(self, code: str, slug: str, agents_dir: str,
                       report: ValidationReport) -> Optional[Dict]:
        """Dynamically import the module and extract TOOL_REGISTRY."""
        module_path = os.path.join(agents_dir, slug, "mcp_tools.py")

        if not os.path.exists(module_path):
            report.add(ValidationSeverity.ERROR, "REGISTRY",
                       f"mcp_tools.py not found at {module_path}")
            return None

        # Ensure backend is on sys.path for shared imports
        backend_dir = os.path.abspath(os.path.join(agents_dir, '..'))
        original_path = sys.path.copy()
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)

        try:
            # Create a unique module name to avoid caching issues
            module_name = f"_validator_{slug}_{id(report)}"
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                report.add(ValidationSeverity.ERROR, "REGISTRY",
                           "Failed to create module spec for mcp_tools.py")
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            registry = getattr(module, "TOOL_REGISTRY", None)
            if registry is None:
                report.add(ValidationSeverity.ERROR, "REGISTRY",
                           "TOOL_REGISTRY not found in mcp_tools.py. "
                           "The file must export a TOOL_REGISTRY dict.")
                return None

            if not isinstance(registry, dict):
                report.add(ValidationSeverity.ERROR, "REGISTRY",
                           f"TOOL_REGISTRY is {type(registry).__name__}, expected dict.")
                return None

            if not registry:
                report.add(ValidationSeverity.ERROR, "REGISTRY",
                           "TOOL_REGISTRY is empty — no tools defined.")
                return None

            return registry

        except STRUCTURAL_EXCEPTIONS as e:
            report.add(ValidationSeverity.ERROR, "REGISTRY",
                       f"Failed to import mcp_tools.py: {type(e).__name__}: {e}")
            return None
        except NETWORK_EXCEPTIONS as e:
            report.add(ValidationSeverity.WARNING, "REGISTRY",
                       f"Module import triggered network call that failed: {e}. "
                       "Avoid making network calls at module level.")
            return None
        except Exception as e:
            report.add(ValidationSeverity.ERROR, "REGISTRY",
                       f"Unexpected error loading mcp_tools.py: {type(e).__name__}: {e}")
            return None
        finally:
            sys.path = original_path

    def _validate_tool(self, tool_name: str, tool_info: Dict,
                       report: ValidationReport):
        """Validate a single tool entry: structure, execution, and output."""
        report.tools_tested += 1
        tool_passed = True

        # Check required keys
        if "function" not in tool_info:
            report.add(ValidationSeverity.ERROR, "REGISTRY",
                       f"Missing 'function' key.", tool_name=tool_name)
            return

        if not callable(tool_info["function"]):
            report.add(ValidationSeverity.ERROR, "REGISTRY",
                       f"'function' is not callable.", tool_name=tool_name)
            return

        if "description" not in tool_info:
            report.add(ValidationSeverity.WARNING, "REGISTRY",
                       f"Missing 'description' key.", tool_name=tool_name)

        if "input_schema" not in tool_info:
            report.add(ValidationSeverity.WARNING, "REGISTRY",
                       f"Missing 'input_schema' key.", tool_name=tool_name)

        # Generate sample inputs and call the tool
        schema = tool_info.get("input_schema", {"type": "object", "properties": {}})
        sample_inputs = self._generate_sample_inputs(schema)

        try:
            result = tool_info["function"](**sample_inputs)
        except NETWORK_EXCEPTIONS as e:
            report.add(ValidationSeverity.WARNING, "EXECUTION",
                       f"Network error during execution (expected for API-dependent tools): "
                       f"{type(e).__name__}: {e}",
                       tool_name=tool_name)
            # Can't validate output, but the tool structure may be fine
            # Do a static check instead
            self._static_check_return_format(tool_info["function"], tool_name, report)
            report.tools_passed += 1
            return
        except STRUCTURAL_EXCEPTIONS as e:
            report.add(ValidationSeverity.ERROR, "EXECUTION",
                       f"Structural error: {type(e).__name__}: {e}",
                       tool_name=tool_name)
            return
        except Exception as e:
            report.add(ValidationSeverity.WARNING, "EXECUTION",
                       f"Execution error: {type(e).__name__}: {e}",
                       tool_name=tool_name)
            self._static_check_return_format(tool_info["function"], tool_name, report)
            report.tools_passed += 1
            return

        # Validate return format
        if not isinstance(result, dict):
            report.add(ValidationSeverity.ERROR, "RETURN_FORMAT",
                       f"Tool returned {type(result).__name__}, expected dict with "
                       f"'_ui_components' and '_data' keys.",
                       tool_name=tool_name)
            return

        if "_ui_components" not in result:
            report.add(ValidationSeverity.ERROR, "RETURN_FORMAT",
                       f"Return dict missing '_ui_components' key. "
                       f"Keys found: {list(result.keys())}",
                       tool_name=tool_name)
            tool_passed = False

        ui_comps = result.get("_ui_components")
        if ui_comps is not None:
            if not isinstance(ui_comps, list):
                report.add(ValidationSeverity.ERROR, "RETURN_FORMAT",
                           f"'_ui_components' is {type(ui_comps).__name__}, expected list.",
                           tool_name=tool_name)
                tool_passed = False
            elif len(ui_comps) == 0:
                report.add(ValidationSeverity.ERROR, "RETURN_FORMAT",
                           f"'_ui_components' is an empty list. "
                           f"Tools must return at least one UI component.",
                           tool_name=tool_name)
                tool_passed = False
            else:
                # Validate each component
                for i, comp in enumerate(ui_comps):
                    if not self._validate_component(comp, tool_name, i, report):
                        tool_passed = False

        if "_data" not in result:
            report.add(ValidationSeverity.WARNING, "RETURN_FORMAT",
                       f"Return dict missing '_data' key (recommended for LLM context).",
                       tool_name=tool_name)

        if tool_passed:
            report.tools_passed += 1

    def _validate_component(self, comp: Any, tool_name: str, index: int,
                            report: ValidationReport) -> bool:
        """Validate a single component dict. Returns True if valid."""
        if not isinstance(comp, dict):
            report.add(ValidationSeverity.ERROR, "COMPONENT",
                       f"Component [{index}] is {type(comp).__name__}, expected dict. "
                       f"Did you forget to call .to_json()?",
                       tool_name=tool_name)
            return False

        comp_type = comp.get("type")
        if not comp_type:
            report.add(ValidationSeverity.ERROR, "COMPONENT",
                       f"Component [{index}] missing 'type' field.",
                       tool_name=tool_name)
            return False

        if comp_type not in VALID_COMPONENT_TYPES:
            report.add(ValidationSeverity.ERROR, "COMPONENT",
                       f"Component [{index}] has unknown type '{comp_type}'. "
                       f"Valid types: {sorted(VALID_COMPONENT_TYPES)}",
                       tool_name=tool_name)
            return False

        # Validate field names against the spec
        spec_fields = PRIMITIVES_SPEC.get(comp_type, {}).get("fields", {})
        for key in comp:
            if key not in spec_fields and key not in ("type", "id", "style"):
                report.add(ValidationSeverity.WARNING, "COMPONENT",
                           f"Component [{index}] (type='{comp_type}') has unknown "
                           f"field '{key}'. Expected fields: {list(spec_fields.keys())}",
                           tool_name=tool_name)

        # Check for common mistakes
        if comp_type == "card" and "children" in comp and "content" not in comp:
            report.add(ValidationSeverity.ERROR, "COMPONENT",
                       f"Card component [{index}] uses 'children' but Card expects 'content'. "
                       f"Change 'children' to 'content'.",
                       tool_name=tool_name)
            return False

        # Recursively validate nested components
        valid = True
        for container_field in ("content", "children"):
            nested = comp.get(container_field)
            if isinstance(nested, list):
                for j, child in enumerate(nested):
                    if isinstance(child, dict) and "type" in child:
                        if not self._validate_component(child, tool_name,
                                                         f"{index}.{container_field}[{j}]",
                                                         report):
                            valid = False

        return valid

    def _generate_sample_inputs(self, schema: Dict) -> Dict[str, Any]:
        """Generate sample inputs from a JSON schema."""
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        sample = {}

        for name, prop in props.items():
            prop_type = prop.get("type", "string")
            enum = prop.get("enum")

            if enum:
                sample[name] = enum[0]
            elif prop_type == "string":
                sample[name] = prop.get("default", "sample")
            elif prop_type in ("number", "integer"):
                sample[name] = prop.get("default", 42)
            elif prop_type == "boolean":
                sample[name] = prop.get("default", True)
            elif prop_type == "array":
                sample[name] = prop.get("default", [])
            elif prop_type == "object":
                sample[name] = prop.get("default", {})
            else:
                sample[name] = "sample"

        return sample

    def _static_check_return_format(self, func, tool_name: str,
                                     report: ValidationReport):
        """When a tool can't be executed, do a static AST check for return format."""
        try:
            import inspect
            source = inspect.getsource(func)
            if "_ui_components" not in source:
                report.add(ValidationSeverity.ERROR, "RETURN_FORMAT",
                           f"Source code does not contain '_ui_components'. "
                           f"Tool likely doesn't return the required format.",
                           tool_name=tool_name)
            if ".to_json()" not in source and "to_json" not in source:
                report.add(ValidationSeverity.WARNING, "RETURN_FORMAT",
                           f"Source code doesn't call '.to_json()'. "
                           f"Components may not be serialized correctly.",
                           tool_name=tool_name)
        except (OSError, TypeError):
            pass  # Can't inspect source, skip static check
