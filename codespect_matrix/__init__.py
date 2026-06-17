"""codespect-matrix — Multi-Agent Code Evolution Platform with Deep Taint Analysis

CPG Analysis · 10-Stage Pipeline · Debate Review · Harness Engineering · Self-Evolution

Key Features:
- 20+ specialized agents: Security, Healthcare, PHI, FHIR, DICOM, HL7, CDS,
  Compliance, Architecture, Performance, DevOps, Testing, Linter, Data Science,
  Hardcode, Concurrency, API, Dependency, DB Compatibility, DB Schema,
  API Contract, Smoke Test
- 10-stage pipeline: CPG Deep Taint → Agent Selection → Parallel Inspection →
  Harness Validation → Cross-Review → Harness Verification → Debate Arbitration →
  Convergence Detection → Drift Detection → Fix Generation → Evolution Report
- CPG (Code Property Graph) pre-scan: AST + Call Graph + Data Flow + Taint
  Analysis, pure Python, zero external dependencies
- Harness Engineering: Constraint enforcement, cross-phase verification,
  feedback routing, automatic recovery, drift detection
- Dynamic Analysis: DB schema consistency, API contract validation, smoke testing
- Debate validation: Multi-round cross-examination with confidence thresholds
- Hybrid engine: Rule engine + LLM reasoning + CPG taint analysis
- Dual memory: ProjectMemory + GlobalKnowledgeBase (cross-project learning)
- Self-Evolution: QA → Fix → ReQA → Learn closed loop
- Code evolution: Health score · Technical debt · Architecture health · Roadmap

Usage:
    # Default multi-agent review (10-stage pipeline)
    codespect-matrix

    # Code evolution analysis
    codespect-matrix --evolve

    # Full review with JSON output
    codespect-matrix --max-rounds 3 --json

    # AI autonomous fix
    codespect-matrix --fix-plan && codespect-matrix --fix-execute

    # Python API
    from codespect_matrix.agents import AgentOrchestrator
    orch = AgentOrchestrator(project_path="/my/project")
    orch.initialize()
    result = orch.run_full_cycle()
"""

__version__ = "3.0.0"
__author__ = "周良"
__organization__ = "上海交通大学医学院"

# Core
from .scanner import ProjectScanner
from .models import ProjectProfile
from .llm_service import LLMService, create_llm_service, get_llm_service
from .cli import main as cli_main

# Agent architecture
from .agents import (
    BaseAgent, AgentMessage, DebateResult, AgentRole,
    AgentCommunicationBus,
    ProjectMemory, GlobalKnowledgeBase,
    AgentOrchestrator,
)

# Evolution engine
from .evolution import (
    HealthScorer, TechDebtAnalyzer, ArchitectureAnalyzer,
    TestCoverageEstimator, EvolutionReporter, EvolutionBaseline,
    SelfEvolver,
)

# Fix engine
from .fix_engine import FixEngine, FixResult, run_fix_cycle

__all__ = [
    # Core
    "ProjectScanner", "ProjectProfile",
    "LLMService", "create_llm_service", "get_llm_service",
    "cli_main",
    # Agent architecture
    "BaseAgent", "AgentMessage", "DebateResult", "AgentRole",
    "AgentCommunicationBus",
    "ProjectMemory", "GlobalKnowledgeBase",
    "AgentOrchestrator",
    # Evolution engine
    "HealthScorer", "TechDebtAnalyzer", "ArchitectureAnalyzer",
    "TestCoverageEstimator", "EvolutionReporter", "EvolutionBaseline",
    "SelfEvolver",
    # Fix engine
    "FixEngine", "FixResult", "run_fix_cycle",
]
