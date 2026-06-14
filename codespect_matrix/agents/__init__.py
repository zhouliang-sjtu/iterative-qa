"""codespect-matrix multi-agent architecture.

Debate review + hybrid mode (rule engine + LLM reasoning) + dual memory.

Modules:
- base: Agent base class, message protocol, debate results
- bus: Agent communication bus
- memory: Project-level memory + global knowledge base
- rule_agents: Security/Healthcare/PHI/Compliance/MedicalData — rule+LLM hybrid
- llm_agents: Remaining domains — pure LLM + linter + datascience + hardcode
- orchestrator: Workflow coordinator, manages full review cycle
"""

from .base import BaseAgent, AgentMessage, DebateResult, AgentRole
from .bus import AgentCommunicationBus
from .memory import ProjectMemory, GlobalKnowledgeBase
from .orchestrator import AgentOrchestrator
from .rule_agents import SecurityAgent, HealthcareAgent, PHIAgent, ComplianceAgent, MedicalDataAgent
from .llm_agents import LinterAgent, DatascienceAgent, HardcodeAgent

__all__ = [
    "BaseAgent", "AgentMessage", "DebateResult", "AgentRole",
    "AgentCommunicationBus",
    "ProjectMemory", "GlobalKnowledgeBase",
    "AgentOrchestrator",
    "SecurityAgent", "HealthcareAgent", "PHIAgent", "ComplianceAgent", "MedicalDataAgent",
    "LinterAgent", "DatascienceAgent", "HardcodeAgent",
]
