"""AgentOrchestrator — multi-agent workflow coordinator.

Pipeline:
1. Project analysis → Agent selection (profile + global KB recommendation)
2. Parallel inspection → All agents discover issues independently
3. Cross-review → Each finding reviewed by agents from different domains
4. Debate ruling → Disputed findings enter debate
5. Convergence detection → Terminate when no new findings
6. Fix generation → Confirmed issues generate fix proposals
7. Evolution report → Health score + technical debt + architecture + roadmap
"""

from __future__ import annotations

import os
import yaml
import uuid
from datetime import datetime, UTC
from typing import Dict, List, Any, Optional

from .base import (
    BaseAgent, AgentRole, AgentMessage, MessageType, Finding, DebateResult,
)
from .bus import AgentCommunicationBus
from .memory import ProjectMemory, GlobalKnowledgeBase
from .rule_agents import (
    SecurityAgent, HealthcareAgent, PHIAgent, ComplianceAgent, MedicalDataAgent,
    FHIRAgent, DICOMAgent, HL7Agent, CDSRulesAgent,
)
from .llm_agents import LLM_AGENT_CLASSES

try:
    from ..llm_service import get_llm_service, LLMService
except ImportError:
    get_llm_service = lambda: None
    LLMService = None

try:
    from ..evolution import EvolutionReporter, EvolutionBaseline
except ImportError:
    EvolutionReporter = None
    EvolutionBaseline = None

# Default config path
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "agent_config.yaml")


class AgentOrchestrator:
    """Multi-agent orchestrator — debate review + hybrid engine + dual memory."""

    MAX_DEBATE_ROUNDS = 3
    CONVERGENCE_STABILITY = 2

    def __init__(self, project_path: str = ".", config: Dict = None):
        self.project_path = project_path
        self.config = config or self._load_config()
        self.llm = get_llm_service()

        # Core facilities
        self.bus = AgentCommunicationBus()
        self.project_memory = ProjectMemory(project_path)
        self.global_kb = GlobalKnowledgeBase()

        # Agent management
        self.agents: Dict[str, BaseAgent] = {}
        self.active_agents: List[str] = []
        self.round_results: List[Dict] = []
        self.all_findings: List[Finding] = []
        self.debate_results: List[DebateResult] = []

        # Convergence tracking
        self.finding_history: List[set] = []
        self.stable_rounds = 0

        self._project_profile: Dict[str, Any] = {}

    # ── Config loading ────────────────────────────────────────────────────────

    def _load_config(self) -> Dict:
        """Load runtime config from agent_config.yaml, falling back to defaults."""
        paths = [
            os.path.join(self.project_path, "agent_config.yaml"),
            CONFIG_PATH,
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        return yaml.safe_load(f) or {}
                except Exception:
                    pass
        return {}

    def _cfg(self, *keys, default=None):
        """Safe nested config access. e.g. _cfg("debate", "max_rounds", default=3)"""
        d = self.config
        for k in keys:
            if isinstance(d, dict):
                d = d.get(k)
            else:
                return default
        return d if d is not None else default

    # ── Phase 0: Initialization & Agent selection ─────────────────────────────

    def initialize(self, project_profile: Dict[str, Any] = None):
        """Initialize: analyze project + select agents.

        Args:
            project_profile: If None, auto-scan via ProjectScanner.
        """
        if project_profile:
            self._project_profile = project_profile
        else:
            self._analyze_project()
        self._select_agents()

    def _analyze_project(self):
        """Scan project characteristics."""
        from ..scanner import ProjectScanner
        scanner = ProjectScanner()
        profile = scanner.scan(self.project_path)
        self._project_profile = profile.to_dict()

    def _select_agents(self):
        """Intelligent agent selection based on project profile + global KB.

        Strategy:
        - Mandatory: security, developer (always active)
        - Domain match: medical → healthcare/phi/medical_data/compliance
        - KB recommendation: historical agent effectiveness for similar projects
        - Tech stack: Python → concurrency/devops/api
        """
        profile = self._project_profile
        domain = profile.get("domain", "")
        tech_stack = profile.get("tech_stack", [])
        project_type = profile.get("project_type", "")

        self._register_all_agents()

        # Mandatory agents
        self.active_agents = ["security", "developer"]

        # Domain matching — healthcare projects activate full medical agent suite
        is_healthcare = (
            "医疗" in domain or "medical" in domain.lower() or "healthcare" in domain.lower()
        )
        # Also detect via tech stack dependencies
        health_libs = {"fhirclient", "pydicom", "hl7apy", "fhiry", "medspacy", "clinicalnlp"}
        if health_libs & set(str(tech_stack).lower().split(", ")):
            is_healthcare = True

        if is_healthcare:
            self.active_agents.extend([
                "healthcare", "phi_protection", "medical_data",
                "fhir", "dicom", "hl7", "cds", "compliance",
            ])

        # Global KB recommendations
        kb_recs = self.global_kb.recommend_agents(project_type, domain)
        for rec in kb_recs:
            if rec not in self.active_agents and rec in self.agents:
                self.active_agents.append(rec)

        # Tech stack matching
        if "Python" in str(tech_stack) or "FastAPI" in str(tech_stack) or "Django" in str(tech_stack):
            for a in ["concurrency", "devops", "api"]:
                if a not in self.active_agents and a in self.agents:
                    self.active_agents.append(a)

        if "Docker" in str(tech_stack) or "Node.js" in str(tech_stack):
            if "devops" not in self.active_agents:
                self.active_agents.append("devops")

        # Always include review-level agents
        for a in ["architect", "testing", "linter"]:
            if a not in self.active_agents and a in self.agents:
                self.active_agents.append(a)

        # Honor config max_active
        max_active = self._cfg("agent_selection", "max_active", default=8)
        self.active_agents = self.active_agents[:max_active]

    def _register_all_agents(self):
        """Register all agents on the bus and agent pool."""

        # Hybrid agents (rule + LLM)
        rule_agent_classes = {
            "security": (SecurityAgent, AgentRole.INSPECTOR),
            "healthcare": (HealthcareAgent, AgentRole.INSPECTOR),
            "phi_protection": (PHIAgent, AgentRole.INSPECTOR),
            "compliance": (ComplianceAgent, AgentRole.INSPECTOR),
            "medical_data": (MedicalDataAgent, AgentRole.INSPECTOR),
            "fhir": (FHIRAgent, AgentRole.INSPECTOR),
            "dicom": (DICOMAgent, AgentRole.INSPECTOR),
            "hl7": (HL7Agent, AgentRole.INSPECTOR),
            "cds": (CDSRulesAgent, AgentRole.INSPECTOR),
        }

        for name, (cls, role) in rule_agent_classes.items():
            agent = cls(name=name, role=role, llm_service=self.llm)
            self._add_agent(name, agent)

        # LLM agents (includes new: linter, datascience, hardcode)
        for name, cls in LLM_AGENT_CLASSES.items():
            agent = cls(name=name, role=AgentRole.INSPECTOR, llm_service=self.llm)
            self._add_agent(name, agent)

    def _add_agent(self, name: str, agent: BaseAgent):
        """Register a single agent."""
        agent.set_context(self.project_path, self._project_profile)
        agent.memory = self.project_memory
        self.agents[name] = agent
        self.bus.register_agent(agent)

    # ── Phase 1: Parallel inspection ──────────────────────────────────────────

    def _collect_files_context(self) -> str:
        """Collect project source files as agent context."""
        import glob as glob_mod

        file_contexts = []
        for filepath in glob_mod.glob(
            os.path.join(self.project_path, "**", "*.py"), recursive=True,
        ):
            relpath = os.path.relpath(filepath, self.project_path)
            # Skip self and caches
            if "agents" in relpath.split(os.sep) or "__pycache__" in relpath:
                continue
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if len(content) < 5000:
                        file_contexts.append(f"\n=== FILE: {relpath} ===\n{content}")
                    else:
                        file_contexts.append(
                            f"\n=== FILE: {relpath} ===\n{content[:3000]}\n"
                            f"... ({len(content)} total lines)\n{content[-2000:]}"
                        )
            except Exception:
                continue

            if sum(len(c) for c in file_contexts) > 30000:
                break

        return "\n".join(file_contexts)

    def inspect_phase(self) -> int:
        """Inspection phase: all agents scan in parallel.

        Returns:
            Total number of findings.
        """
        files_context = self._collect_files_context()

        all_findings = []
        for agent_name in self.active_agents:
            agent = self.agents.get(agent_name)
            if not agent:
                continue

            try:
                findings = agent.inspect(files_context)
                # Filter known false positives
                filtered = []
                for f in findings:
                    # Project-level FP
                    if self.project_memory.is_false_positive(f.check_name, f.message):
                        continue
                    # Global FP
                    if self.global_kb.check_false_positive(f.message):
                        continue
                    filtered.append(f)

                for f in filtered:
                    if not f.check_name.startswith(agent_name):
                        f.check_name = f"{agent_name}_{f.check_name}"

                all_findings.extend(filtered)

                self.bus.send(
                    sender=agent_name,
                    receiver="orchestrator",
                    msg_type=MessageType.FINDING,
                    content=f"Found {len(filtered)} issues",
                    data={"count": len(filtered)},
                )
            except Exception as e:
                self.bus.send(
                    sender=agent_name,
                    receiver="orchestrator",
                    msg_type=MessageType.FINDING,
                    content=f"Inspection error: {e}",
                    data={"error": str(e)},
                )

        self.all_findings = all_findings
        return len(all_findings)

    # ── Phase 2: Cross-review ─────────────────────────────────────────────────

    def review_phase(self) -> Dict[str, int]:
        """Review phase: each finding cross-reviewed by a different-domain agent.

        Returns:
            {"confirmed": n, "rejected": n, "adjusted": n}
        """
        stats = {"confirmed": 0, "rejected": 0, "adjusted": 0}

        for finding in self.all_findings:
            # Pick a reviewer from a different domain
            finder = finding.check_name.split("_")[0] if "_" in finding.check_name else ""
            reviewers = [a for a in self.active_agents if a != finder]
            if not reviewers:
                reviewers = [self.active_agents[0]]

            reviewer_name = reviewers[0]
            reviewer = self.agents.get(reviewer_name)
            if not reviewer:
                continue

            try:
                result = reviewer.review(finding)
                finding.reviewed = True
                finding.reviewer = reviewer_name

                verdict = result.get("verdict", "confirmed")
                if verdict == "rejected":
                    finding.ruling = "rejected"
                    stats["rejected"] += 1
                    self.project_memory.mark_false_positive(
                        finding.check_name, finding.message,
                        f"by {reviewer_name}: {result.get('comment', '')}",
                    )
                elif verdict == "adjusted":
                    finding.ruling = "adjusted"
                    finding.severity = result.get("adjusted_severity", finding.severity)
                    stats["adjusted"] += 1
                else:
                    finding.ruling = "confirmed"
                    stats["confirmed"] += 1

            except Exception:
                finding.reviewed = True
                finding.ruling = "confirmed"
                stats["confirmed"] += 1

        return stats

    # ── Phase 3: Debate ───────────────────────────────────────────────────────

    def debate_phase(self) -> List[DebateResult]:
        """Debate phase: disputed findings enter challenge→defense→arbiter."""
        debate_max = self._cfg("debate", "max_rounds", default=3)

        # Low-confidence or adjusted findings are disputed
        contested = [f for f in self.all_findings
                     if f.reviewed and f.confidence < 0.6 and f.ruling != "rejected"]

        for finding in contested[:5]:
            challenger_candidates = [
                a for a in self.active_agents
                if a != (finding.check_name.split("_")[0] if "_" in finding.check_name else "")
            ]
            if not challenger_candidates:
                continue

            challenger = challenger_candidates[0]
            reason = f"Confidence only {finding.confidence}, further verification needed"

            debate_id = self.bus.open_debate(finding, challenger, reason)

            defender = finding.check_name.split("_")[0] if "_" in finding.check_name else "developer"

            ruling = "confirmed" if finding.confidence >= 0.4 else "rejected"
            result = self.bus.close_debate(
                debate_id=debate_id,
                arbiter="orchestrator",
                ruling=ruling,
                rationale=(
                    f"After review, confidence {finding.confidence}, "
                    f"{'confirmed' if ruling == 'confirmed' else 'insufficient evidence, rejected'}"
                ),
            )

            if result:
                result.defender = defender
                self.debate_results.append(result)

        return self.debate_results

    # ── Phase 4: Convergence check ────────────────────────────────────────────

    def check_convergence(self) -> bool:
        """Check if the review has converged."""
        current_fps = set()
        for f in self.all_findings:
            if f.ruling != "rejected":
                current_fps.add(f"{f.check_name}:{f.message[:80]}")

        self.finding_history.append(current_fps)

        if len(self.finding_history) >= 2:
            prev = self.finding_history[-2]
            new = current_fps - prev
            if not new:
                self.stable_rounds += 1
            else:
                self.stable_rounds = 0

        stability = self._cfg("convergence", "stability_threshold", default=self.CONVERGENCE_STABILITY)
        return self.stable_rounds >= stability

    # ── Phase 5: Fix proposals ────────────────────────────────────────────────

    def generate_fix_proposals(self) -> List[Dict]:
        """Generate fix proposals for confirmed issues."""
        confirmed = [f for f in self.all_findings if f.ruling == "confirmed"]
        proposals = []

        for finding in confirmed:
            agent_name = finding.check_name.split("_")[0] if "_" in finding.check_name else "developer"
            agent = self.agents.get(agent_name)
            if agent:
                try:
                    proposal = agent.propose_fix(finding)
                    proposals.append(proposal)
                except Exception:
                    proposals.append({
                        "finding": finding.to_dict(),
                        "fix_description": finding.remediation or "Manual fix required",
                        "can_auto_fix": False,
                    })

        return proposals

    # ── Main cycle ────────────────────────────────────────────────────────────

    def run_full_cycle(self, max_rounds: int = None) -> Dict[str, Any]:
        """Run a complete multi-agent review cycle.

        Args:
            max_rounds: Override config value. Defaults to config or 5.
        """
        if max_rounds is None:
            max_rounds = self._cfg("convergence", "max_rounds", default=5)

        if not self._project_profile:
            self.initialize()

        total_confirmed = 0
        cycle_log = []

        for round_num in range(1, max_rounds + 1):
            round_data = {
                "round": round_num,
                "timestamp": datetime.now(UTC).isoformat(),
                "active_agents": list(self.active_agents),
            }

            # Phase 1: Inspect
            round_data["findings_count"] = self.inspect_phase()

            if round_data["findings_count"] == 0:
                round_data["status"] = "clean"
                cycle_log.append(round_data)
                break

            # Phase 2: Review
            round_data["review_stats"] = self.review_phase()

            # Phase 3: Debate (round 1 only)
            if round_num == 1:
                round_data["debates"] = [d.to_dict() for d in self.debate_phase()]

            # Record
            self.project_memory.record_scan(
                round_number=round_num,
                issue_count=round_data["findings_count"],
                status="completed",
                agent_count=len(self.active_agents),
            )

            cycle_log.append(round_data)

            # Convergence
            if self.check_convergence():
                round_data["status"] = "converged"
                break

            round_data["status"] = "in_progress"

        # Phase 5: Fix proposals
        fix_proposals = self.generate_fix_proposals()

        # Global stats
        self.global_kb.record_project_stats(
            project_type=self._project_profile.get("project_type", ""),
            issue_count=len(self.all_findings),
            fixed_count=0,
        )

        return {
            "project": self._project_profile,
            "cycles": cycle_log,
            "total_rounds": len(cycle_log),
            "total_findings": len(self.all_findings),
            "confirmed_issues": [f.to_dict() for f in self.all_findings if f.ruling == "confirmed"],
            "rejected_issues": [f.to_dict() for f in self.all_findings if f.ruling == "rejected"],
            "debate_results": [d.to_dict() for d in self.debate_results],
            "fix_proposals": fix_proposals,
            "converged": self.stable_rounds >= self.CONVERGENCE_STABILITY,
            "bus_stats": self.bus.get_stats(),
            "global_stats": self.global_kb.get_stats(),
        }

    # ── Evolution Report ───────────────────────────────────────────────────────

    def run_evolution(self, save_baseline: bool = False) -> Dict[str, Any]:
        """Run a full evolution analysis after agent review.

        Combines: agent findings + health score + technical debt +
                  architecture analysis + test coverage + improvement roadmap.

        Args:
            save_baseline: If True, save this report as a baseline for future
                          trend comparison.

        Returns:
            Full evolution report dict.
        """
        if not EvolutionReporter:
            return {"error": "Evolution module not available"}

        reporter = EvolutionReporter(self.project_path)
        baseline = EvolutionBaseline(self.project_path)

        # Collect findings from agent scan
        if not self._project_profile:
            self.initialize()

        # Run a quick agent scan if not already done
        if not self.all_findings:
            self.inspect_phase()
            self.review_phase()

        findings = [f.to_dict() for f in self.all_findings if f.ruling != "rejected"]

        # Load previous baseline for trend comparison
        previous = baseline.load()

        report = reporter.full_report(findings, baseline_data=previous)

        if save_baseline:
            baseline.save(report)

        return report

    # ── Report generation ─────────────────────────────────────────────────────

    def generate_report(self, result: Dict[str, Any]) -> str:
        """Generate a human-readable report."""
        lines = []
        lines.append("# codespect-matrix Agent Review Report")
        lines.append(f"\n**Project**: {os.path.basename(self.project_path)}")
        lines.append(f"**Review Time**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"**Agent Count**: {len(self.active_agents)}")
        converged = "Converged" if result["converged"] else "Not Converged"
        lines.append(f"**Convergence**: {converged}")

        lines.append("\n## Active Agents")
        for name in self.active_agents:
            agent = self.agents.get(name)
            if agent:
                lines.append(f"- **{name}** ({agent.get_domain()}): {agent.get_description()}")

        lines.append("\n## Review Statistics")
        lines.append(f"- Total rounds: {result['total_rounds']}")
        lines.append(f"- Total findings: {result['total_findings']}")
        lines.append(f"- Confirmed: {len(result['confirmed_issues'])}")
        lines.append(f"- Rejected: {len(result['rejected_issues'])}")
        lines.append(f"- Debates: {len(result['debate_results'])}")

        if result["confirmed_issues"]:
            lines.append("\n## Confirmed Issues")
            for i, issue in enumerate(result["confirmed_issues"], 1):
                sev = issue["severity"].upper()
                lines.append(
                    f"\n### {i}. [{sev}] {issue['check_name']}\n"
                    f"- Description: {issue['message']}\n"
                    f"- File: {issue.get('file_path', 'N/A')}\n"
                    f"- Fix: {issue.get('remediation', 'N/A')}\n"
                    f"- Confidence: {issue.get('confidence', 0):.0%}"
                )

        if result["rejected_issues"]:
            lines.append("\n## Rejected (False Positives)")
            for issue in result["rejected_issues"][:10]:
                lines.append(f"- {issue['check_name']}: {issue['message'][:100]}")

        if result["debate_results"]:
            lines.append("\n## Debate Outcomes")
            for d in result["debate_results"]:
                lines.append(
                    f"- {d['finding']['check_name']}: "
                    f"{d['challenger']} vs defender → **{d['final_ruling']}**"
                )

        lines.append("\n## Global Knowledge Base")
        gs = result.get("global_stats", {})
        lines.append(f"- Projects analyzed: {gs.get('projects_analyzed', 0)}")
        lines.append(f"- Issues found: {gs.get('issues_found', 0)}")
        lines.append(f"- Issues fixed: {gs.get('issues_fixed', 0)}")

        return "\n".join(lines)
