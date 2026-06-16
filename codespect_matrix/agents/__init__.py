"""codespect-matrix multi-agent architecture — v2.0.

CPG Pre-scan + 10-Stage Pipeline + Debate Review + Harness Engineering + Dynamic Analysis.

Modules:
- base: Agent base class, message protocol, debate results
- bus: Agent communication bus
- memory: Project-level memory + global knowledge base
- orchestrator: 10-stage workflow coordinator (CPG → Select → Inspect → Harness → Review → Verify → Debate → Converge → Drift → Fix → Evolve)
- harness: Constraint enforcement, cross-phase verification, feedback routing, drift detection
- cpg_analyzer: Code Property Graph — AST + Call Graph + Data Flow + Taint Analysis (pure Python)
- rule_agents: Security/Healthcare/PHI/Compliance/MedicalData/FHIR/DICOM/HL7/CDS — rule+LLM hybrid
- healthcare_rules: Deterministic healthcare rule engine (PHI, HIPAA, ICD, FHIR, DICOM, HL7, CDS)
- llm_agents: AI/Architecture/Performance/DevOps/Testing/API/Concurrency/Dependency/Linter/DataScience/Hardcode — pure LLM
- dynamic_agents: Runtime-aware agents — DBCompatibility/DBSchema/APIContract/SmokeTest
- llm_judge: LLM-based cross-domain review judge
"""

from .base import BaseAgent, AgentMessage, DebateResult, AgentRole
from .bus import AgentCommunicationBus
from .memory import ProjectMemory, GlobalKnowledgeBase
from .orchestrator import AgentOrchestrator
from .rule_agents import SecurityAgent, HealthcareAgent, PHIAgent, ComplianceAgent, MedicalDataAgent
from .llm_agents import LinterAgent, DatascienceAgent, HardcodeAgent
from .dynamic_agents import (
    DBCompatibilityAgent, DBSchemaAgent, APIContractAgent, SmokeTestAgent,
    DYNAMIC_AGENT_CLASSES,
)

__all__ = [
    "BaseAgent", "AgentMessage", "DebateResult", "AgentRole",
    "AgentCommunicationBus",
    "ProjectMemory", "GlobalKnowledgeBase",
    "AgentOrchestrator",
    "SecurityAgent", "HealthcareAgent", "PHIAgent", "ComplianceAgent", "MedicalDataAgent",
    "LinterAgent", "DatascienceAgent", "HardcodeAgent",
    # Dynamic analysis agents
    "DBCompatibilityAgent", "DBSchemaAgent", "APIContractAgent", "SmokeTestAgent",
    "DYNAMIC_AGENT_CLASSES",
]
