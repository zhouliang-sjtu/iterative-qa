"""Agent base classes, message protocol, and debate results."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Dict, List, Any, Optional, Callable


class AgentRole(Enum):
    """Agent role taxonomy."""
    INSPECTOR = "inspector"       # Discovers issues
    REVIEWER = "reviewer"         # Evaluates others' findings
    ARBITER = "arbiter"           # Makes final rulings
    FIXER = "fixer"               # Generates fix plans
    ORCHESTRATOR = "orchestrator" # Coordinates globally


class MessageType(Enum):
    """Message type taxonomy."""
    FINDING = "finding"
    REVIEW = "review"
    CHALLENGE = "challenge"
    DEFENSE = "defense"
    RULING = "ruling"
    FIX_PROPOSAL = "fix_proposal"
    CONVERGENCE = "convergence"


@dataclass
class AgentMessage:
    """Inter-agent communication message."""
    id: str
    sender: str
    receiver: str                # "all" for broadcast
    msg_type: MessageType
    content: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    reply_to: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "sender": self.sender, "receiver": self.receiver,
            "msg_type": self.msg_type.value, "content": self.content,
            "data": self.data, "timestamp": self.timestamp.isoformat(),
            "reply_to": self.reply_to,
        }


@dataclass
class Finding:
    """An issue discovered by an agent."""
    check_name: str
    severity: str               # critical/high/medium/low/info
    message: str
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    evidence: str = ""
    remediation: str = ""
    confidence: float = 1.0     # 0.0-1.0
    reviewer: str = ""
    reviewed: bool = False
    ruling: str = ""            # confirmed/rejected/deferred

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_name": self.check_name, "severity": self.severity,
            "message": self.message, "file_path": self.file_path,
            "line_start": self.line_start, "line_end": self.line_end,
            "evidence": self.evidence, "remediation": self.remediation,
            "confidence": self.confidence, "reviewer": self.reviewer,
            "reviewed": self.reviewed, "ruling": self.ruling,
        }


@dataclass
class DebateResult:
    """Outcome of a debate session."""
    finding: Finding
    challenger: str
    defender: str
    arbiter: str
    rounds: List[Dict] = field(default_factory=list)
    final_ruling: str = ""      # confirmed/rejected/deferred
    rationale: str = ""
    new_severity: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding": self.finding.to_dict(), "challenger": self.challenger,
            "defender": self.defender, "arbiter": self.arbiter,
            "rounds": self.rounds, "final_ruling": self.final_ruling,
            "rationale": self.rationale, "new_severity": self.new_severity,
        }


class BaseAgent(ABC):
    """Base agent with core capabilities: inspect, review, debate, fix.

    Subclasses must implement get_description(), get_domain(), and inspect().
    """

    def __init__(self, name: str, role: AgentRole, llm_service=None, bus=None):
        self.name = name
        self.role = role
        self.llm = llm_service
        self.bus = bus
        self.project_path = ""
        self.project_profile: Dict[str, Any] = {}
        self.memory: Any = None
        self.findings: List[Finding] = []
        self._message_id = 0

    @abstractmethod
    def get_description(self) -> str:
        """Human-readable description of this agent's purpose."""
        pass

    @abstractmethod
    def get_domain(self) -> str:
        """Domain this agent specializes in."""
        pass

    def set_context(self, project_path: str, project_profile: Dict[str, Any]):
        """Set project context before inspection."""
        self.project_path = project_path
        self.project_profile = project_profile

    def _next_msg_id(self) -> str:
        self._message_id += 1
        return f"{self.name}_{self._message_id}"

    # ── Phase 1: Inspection ──
    @abstractmethod
    def inspect(self, files_context: str) -> List[Finding]:
        """Scan code and return findings.

        Args:
            files_context: Summary of project files as plain text.

        Returns:
            List of Finding objects.
        """
        pass

    # ── Phase 2: Cross-review ──
    def review(self, finding: Finding) -> Dict[str, Any]:
        """Review a finding from another agent.

        Returns:
            {"verdict": "confirmed"|"rejected"|"adjusted",
             "confidence": 0.0-1.0, "comment": str,
             "adjusted_severity": str (if applicable)}
        """
        return {
            "verdict": "confirmed",
            "confidence": finding.confidence,
            "comment": f"[{self.name}] Default confirm.",
            "adjusted_severity": finding.severity,
        }

    # ── Phase 3: Debate ──
    def challenge(self, finding: Finding, reason: str) -> AgentMessage:
        """Challenge a finding."""
        return AgentMessage(
            id=self._next_msg_id(),
            sender=self.name,
            receiver="orchestrator",
            msg_type=MessageType.CHALLENGE,
            content=f"Challenge {finding.check_name}: {reason}",
            data={"finding": finding.to_dict(), "reason": reason},
        )

    def defend(self, finding: Finding, challenge_msg: AgentMessage) -> AgentMessage:
        """Defend a finding against a challenge."""
        return AgentMessage(
            id=self._next_msg_id(),
            sender=self.name,
            receiver=challenge_msg.sender,
            msg_type=MessageType.DEFENSE,
            content=f"Defense for {finding.check_name}",
            data={
                "finding": finding.to_dict(),
                "defense": f"Based on static analysis, confidence {finding.confidence}",
            },
            reply_to=challenge_msg.id,
        )

    # ── Phase 4: Fix generation ──
    def propose_fix(self, finding: Finding) -> Dict[str, Any]:
        """Generate a fix proposal for a confirmed finding.

        Findings with file_path and line info are marked auto-fixable;
        FixEngine will generate the actual code patch via LLM.
        """
        file_path = finding.file_path
        has_location = bool(file_path and (finding.line_start > 0 or finding.evidence))
        return {
            "finding": finding.to_dict(),
            "fix_description": finding.remediation or "Manual review required",
            "can_auto_fix": has_location,
            "file_path": file_path,
            "line_start": finding.line_start,
            "line_end": finding.line_end,
            "old_code": finding.evidence or "",
            "new_code": "",
        }

    def __repr__(self):
        return f"<{self.role.value}:{self.name}>"
