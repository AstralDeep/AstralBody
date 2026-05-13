"""
Proactive Tool Security Analyzer for the AstralBody Orchestrator.

Analyzes agent tool declarations (name, description, input_schema) for
patterns that indicate nefarious behavior. Runs automatically when agents
register, before any user interaction.

Threat categories:
  - DATA_EGRESS:           External data transmission
  - CODE_EXECUTION:        Arbitrary code/script/command execution
  - CREDENTIAL_ACCESS:     Access to secrets, API keys, tokens
  - DESTRUCTIVE:           Deletion, wiping, or corruption of data
  - PRIVILEGE_ESCALATION:  Modification of permissions/roles/admin access
  - NETWORK_MANIPULATION:  DNS, firewall, routing changes
"""
import re
import logging
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger("ToolSecurity")


# =============================================================================
# Data Structures
# =============================================================================

class ThreatCategory(str, Enum):
    DATA_EGRESS = "DATA_EGRESS"
    CODE_EXECUTION = "CODE_EXECUTION"
    CREDENTIAL_ACCESS = "CREDENTIAL_ACCESS"
    DESTRUCTIVE = "DESTRUCTIVE"
    PRIVILEGE_ESCALATION = "PRIVILEGE_ESCALATION"
    NETWORK_MANIPULATION = "NETWORK_MANIPULATION"


@dataclass
class SecurityFlag:
    """A security flag raised against a specific tool."""
    tool_name: str
    category: ThreatCategory
    reason: str
    blocked: bool = True  # system-level block

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "category": self.category.value,
            "reason": self.reason,
            "blocked": self.blocked,
        }


# =============================================================================
# Threat Pattern Definitions
# =============================================================================

THREAT_PATTERNS: List[Dict[str, Any]] = [
    # DATA_EGRESS — tools that send/transmit/exfiltrate data externally
    {
        "category": ThreatCategory.DATA_EGRESS,
        "name_patterns": [
            r"exfiltrat",
            r"send_(?:data|info|report)_(?:to|external)",
            r"upload_(?:data|file)_(?:external|remote)",
            r"transmit_(?:data|info)",
            r"webhook_(?:send|post|push)",
            r"phone_home",
            r"beacon",
        ],
        "desc_patterns": [
            r"(?:send|transmit|post|upload|exfiltrat)\w*\s+(?:to\s+)?(?:an?\s+)?(?:external|remote|outside)\s+(?:endpoint|server|url|domain|api|service)",
            r"(?:send|transmit|post|upload|exfiltrat)\w*\s+(?:user\s+)?data\s+(?:to|externally)",
            r"(?:external|remote)\s+(?:endpoint|server|url|api)\s+(?:transmission|upload|post)",
        ],
        "schema_field_patterns": [
            r"(?:destination|target|exfil)_url",
            r"external_(?:endpoint|url|server)",
            r"webhook_url",
            r"c2_(?:server|url|endpoint)",
        ],
        "reason": "Data egress detected — tool attempts external data transmission",
    },
    # CODE_EXECUTION — tools that write, execute, or eval arbitrary code
    {
        "category": ThreatCategory.CODE_EXECUTION,
        "name_patterns": [
            r"exec(?:ute)?_(?:code|script|command|shell|arbitrary)",
            r"run_(?:code|script|command|shell)",
            r"eval_(?:code|expression|script)",
            r"(?:shell|bash|cmd|powershell)_exec",
            r"inject_(?:code|payload|script)",
        ],
        "desc_patterns": [
            r"(?:execute|run|eval)\w*\s+(?:arbitrary|dynamic|user[- ]supplied|untrusted)\s+(?:code|script|command)",
            r"(?:shell|command[- ]line|terminal)\s+(?:access|execution)",
            r"(?:code|script|payload)\s+(?:injection|execution)",
            r"(?:arbitrary|remote)\s+(?:code|command)\s+execution",
        ],
        "schema_field_patterns": [
            r"(?:code|script|command|payload)_(?:to_execute|content|body|source)",
            r"shell_command",
            r"eval_expression",
        ],
        "reason": "Code execution detected — tool can execute arbitrary code or commands",
    },
    # CREDENTIAL_ACCESS — tools that access secrets, API keys, tokens
    {
        "category": ThreatCategory.CREDENTIAL_ACCESS,
        "name_patterns": [
            r"(?:steal|dump|harvest|extract)_(?:secret|credential|password|key|token)",
            r"credential_(?:harvest|dump|access|steal)",
            r"keylog",
            r"password_(?:dump|spray|harvest)",
        ],
        "desc_patterns": [
            r"(?:steal|harvest|dump|extract)\w*\s+(?:secret|credential|password|api[- ]?key|token|private[- ]?key)",
            r"(?:credential|password|secret|key)\s+(?:harvesting|dumping|stealing|extraction)",
            r"(?:intercept|capture)\w*\s+(?:authentication|credential|token|session)",
        ],
        "schema_field_patterns": [
            r"target_credentials",
            r"dump_(?:passwords|secrets|keys)",
        ],
        "reason": "Credential access detected — tool may steal secrets, API keys, or passwords",
    },
    # DESTRUCTIVE — tools that delete, wipe, truncate, or destroy data
    {
        "category": ThreatCategory.DESTRUCTIVE,
        "name_patterns": [
            r"(?:delete|wipe|truncate|destroy|drop|purge|nuke)_(?:all|data|database|table|user|file|system|everything)",
            r"format_(?:disk|drive|partition)",
            r"ransomware",
            r"(?:mass|bulk)_delet",
        ],
        "desc_patterns": [
            r"(?:delete|wipe|truncate|destroy|drop|purge|erase)\w*\s+(?:all|entire|every|bulk)\s+(?:data|record|file|table|database|user)",
            r"(?:irreversibl|permanent)\w*\s+(?:delet|remov|destroy|eras)",
            r"(?:ransomware|encrypt\w*\s+(?:all|files|data)\s+(?:for\s+ransom|and\s+demand))",
        ],
        "schema_field_patterns": [
            r"confirm_(?:destroy|wipe|delete_all)",
        ],
        "reason": "Destructive operation detected — tool can delete, wipe, or destroy data",
    },
    # PRIVILEGE_ESCALATION — tools that modify permissions/roles/admin access
    {
        "category": ThreatCategory.PRIVILEGE_ESCALATION,
        "name_patterns": [
            r"(?:grant|escalate|elevate)_(?:admin|privilege|root|superuser)",
            r"(?:promote|elevate)_(?:to_admin|privilege|access)",
            r"backdoor",
            r"(?:bypass|disable)_(?:auth|security|acl|permission)",
        ],
        "desc_patterns": [
            r"(?:grant|escalate|elevate)\w*\s+(?:to\s+)?(?:admin|root|superuser|elevated)\s+(?:access|privilege|permission|role)",
            r"(?:bypass|disable|circumvent)\w*\s+(?:auth|security|access\s+control|permission|acl)",
            r"(?:backdoor|rootkit|persistent\s+access)",
        ],
        "schema_field_patterns": [
            r"target_(?:role|privilege|access_level)",
            r"escalate_to",
        ],
        "reason": "Privilege escalation detected — tool can modify permissions, roles, or admin access",
    },
    # NETWORK_MANIPULATION — tools that modify DNS, firewall, routing
    {
        "category": ThreatCategory.NETWORK_MANIPULATION,
        "name_patterns": [
            r"(?:modify|change|poison|spoof)_(?:dns|firewall|route|routing|proxy|arp)",
            r"(?:dns|arp)_(?:poison|spoof)",
            r"(?:open|create)_(?:reverse_shell|tunnel|backdoor_port)",
        ],
        "desc_patterns": [
            r"(?:modify|change|poison|spoof)\w*\s+(?:dns|firewall|routing|network|proxy|arp)\s+(?:rule|config|setting|table|record|entry)",
            r"(?:reverse\s+shell|bind\s+shell|network\s+tunnel)",
            r"(?:man[- ]in[- ]the[- ]middle|mitm)",
        ],
        "schema_field_patterns": [
            r"dns_(?:target|record|entry)",
            r"firewall_(?:rule|port)",
        ],
        "reason": "Network manipulation detected — tool can modify DNS, firewall, or routing rules",
    },
]


# =============================================================================
# Analyzer
# =============================================================================

class ToolSecurityAnalyzer:
    """Analyzes agent tool declarations for security threats.

    Uses regex/keyword pattern matching on tool name, description,
    and input_schema field names to detect potential threats.
    """

    def __init__(self):
        self._compiled_patterns: List[Dict[str, Any]] = []
        for pattern_set in THREAT_PATTERNS:
            compiled = {
                "category": pattern_set["category"],
                "reason": pattern_set["reason"],
                "name_re": [re.compile(p, re.IGNORECASE) for p in pattern_set["name_patterns"]],
                "desc_re": [re.compile(p, re.IGNORECASE) for p in pattern_set["desc_patterns"]],
                "schema_re": [re.compile(p, re.IGNORECASE) for p in pattern_set.get("schema_field_patterns", [])],
            }
            self._compiled_patterns.append(compiled)

    def analyze_tool(
        self,
        tool_name: str,
        description: str,
        input_schema: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[SecurityFlag]:
        """Analyze a single tool for security threats.

        Returns a SecurityFlag if a threat is detected, None otherwise.
        """
        schema_fields = []
        if input_schema and "properties" in input_schema:
            schema_fields = list(input_schema["properties"].keys())
        schema_text = " ".join(schema_fields)

        external_target = ""
        if metadata:
            raw_target = metadata.get("external_target")
            if isinstance(raw_target, str) and raw_target.strip():
                external_target = raw_target.strip()

        def _build_flag(category: ThreatCategory, reason: str, match_kind: str) -> SecurityFlag:
            blocked = True
            final_reason = reason
            # DESTRUCTIVE tools that explicitly act on an external service
            # are advisory-only; the per-user `tools:write` permission is
            # the sole gate.
            if category is ThreatCategory.DESTRUCTIVE and external_target:
                blocked = False
                final_reason = (
                    f"Destructive operation on external service "
                    f"'{external_target}' — gated by user permission, "
                    f"not system-blocked."
                )
            flag = SecurityFlag(
                tool_name=tool_name,
                category=category,
                reason=final_reason,
                blocked=blocked,
            )
            severity = "FLAG" if blocked else "ADVISORY"
            logger.warning(
                f"SECURITY {severity}: {category.value} on tool "
                f"'{tool_name}' ({match_kind}) — {final_reason}"
            )
            return flag

        for pattern_set in self._compiled_patterns:
            # Check tool name
            for regex in pattern_set["name_re"]:
                if regex.search(tool_name):
                    return _build_flag(pattern_set["category"], pattern_set["reason"], "name match")

            # Check description
            for regex in pattern_set["desc_re"]:
                if regex.search(description):
                    return _build_flag(pattern_set["category"], pattern_set["reason"], "description match")

            # Check schema field names
            if schema_text:
                for regex in pattern_set["schema_re"]:
                    if regex.search(schema_text):
                        return _build_flag(pattern_set["category"], pattern_set["reason"], "schema match")

        return None

    def analyze_agent(self, card) -> Dict[str, SecurityFlag]:
        """Analyze all skills in an AgentCard.

        Returns dict of {tool_name: SecurityFlag} for flagged tools only.
        Empty dict means no threats detected.
        """
        flags: Dict[str, SecurityFlag] = {}
        for skill in card.skills:
            flag = self.analyze_tool(
                tool_name=skill.id or skill.name,
                description=skill.description or "",
                input_schema=skill.input_schema,
                metadata=getattr(skill, "metadata", None),
            )
            if flag:
                flags[flag.tool_name] = flag

        if flags:
            logger.warning(
                f"Agent '{card.agent_id}' security review: {len(flags)} flagged "
                f"tool(s): {list(flags.keys())}"
            )
        else:
            logger.info(
                f"Agent '{card.agent_id}' passed security review (0 flags)"
            )

        return flags
