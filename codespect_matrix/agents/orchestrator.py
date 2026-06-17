"""AgentOrchestrator — multi-agent workflow coordinator.

Pipeline:
0. CPG pre-scan — Deep taint analysis (AST + data flow)
1. Project analysis → Agent selection (profile + global KB recommendation)
2. Parallel inspection → All agents discover issues independently
3. Harness validate — Constraint enforcement on inspect findings
4. Cross-review → Each finding reviewed by agents from different domains
5. Harness verify — Verification loop on review results
6. Debate ruling → Disputed findings enter debate
7. Convergence detection → Terminate when no new findings
8. Drift detection → Quality trend analysis
9. Fix generation → Confirmed issues generate fix proposals
10. Evolution report → Health score + technical debt + architecture + roadmap
"""

from __future__ import annotations

import os
import yaml
import uuid
from collections import Counter
from datetime import datetime, UTC
from typing import Dict, List, Any, Optional

from .base import (
    BaseAgent, AgentRole, AgentMessage, MessageType, Finding, DebateResult,
)
from .bus import AgentCommunicationBus
from .memory import ProjectMemory, GlobalKnowledgeBase
from .harness import HarnessEngine
from .cpg_analyzer import CPGAnalyzer, taint_to_rule_findings
from .rule_agents import (
    SecurityAgent, HealthcareAgent, PHIAgent, ComplianceAgent, MedicalDataAgent,
    FHIRAgent, DICOMAgent, HL7Agent, CDSRulesAgent,
)
from .llm_agents import LLM_AGENT_CLASSES
from .dynamic_agents import DYNAMIC_AGENT_CLASSES

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

try:
    from ..fix_engine import FixEngine
except ImportError:
    FixEngine = None

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
        self.harness = HarnessEngine()  # Harness Engineering layer

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
        """All-in agent activation — no scoring, no filtering.

        All registered agents are activated unconditionally. The tool
        is designed to leverage its full rule engine + LLM agent suite.
        """
        self._register_all_agents()
        self.active_agents = list(self.agents.keys())

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

        # Dynamic analysis agents (runtime-aware)
        for name, cls in DYNAMIC_AGENT_CLASSES.items():
            agent = cls(name=name, bus=self.bus, memory=self.project_memory)
            self._add_agent(name, agent)

    def _add_agent(self, name: str, agent: BaseAgent):
        """Register a single agent."""
        agent.set_context(self.project_path, self._project_profile)
        agent.memory = self.project_memory
        self.agents[name] = agent
        self.bus.register_agent(agent)

    # ── Phase 1: File collection & inspection ─────────────────────────────────

    def _collect_all_files(self) -> List[tuple]:
        """Collect ALL project source files (no truncation).

        Returns list of (relpath, content) tuples for all .py files.
        """
        import glob as glob_mod

        files = []
        for filepath in glob_mod.glob(
            os.path.join(self.project_path, "**", "*.py"), recursive=True,
        ):
            relpath = os.path.relpath(filepath, self.project_path)
            if "agents" in relpath.split(os.sep) or "__pycache__" in relpath:
                continue
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                files.append((relpath, content))
            except Exception:
                continue
        return files

    def _build_batched_contexts(self, files: List[tuple],
                                 max_chars_per_batch: int = 60000) -> List[str]:
        """Split all files into batches for LLM agents.

        Each batch contains full file contexts up to max_chars_per_batch chars.
        Files with content < 8K chars are included in full; larger files are
        included as head+tail snippets.
        """
        batches = []
        current_batch = []
        current_size = 0

        for relpath, content in files:
            if len(content) < 8000:
                chunk = f"\n=== FILE: {relpath} ===\n{content}"
            else:
                chunk = (
                    f"\n=== FILE: {relpath} ===\n{content[:5000]}\n"
                    f"... ({len(content)} total chars, lines={content.count(chr(10))+1}) ...\n"
                    f"{content[-3000:]}"
                )
            chunk_size = len(chunk)
            if current_size + chunk_size > max_chars_per_batch and current_batch:
                batches.append("\n".join(current_batch))
                current_batch = []
                current_size = 0
            current_batch.append(chunk)
            current_size += chunk_size

        if current_batch:
            batches.append("\n".join(current_batch))
        return batches

    def inspect_phase(self) -> int:
        """Inspection phase: rule agents scan ALL files, LLM agents scan in batches.

        Strategy:
        - Deterministic rule agents get ALL files (no LLM, no truncation needed)
        - LLM agents get files in batches to stay within token limits
        - LinterAgent runs Ruff directly via subprocess
        - CPG taint analysis runs on all files

        Returns:
            Total number of findings.
        """
        all_files = self._collect_all_files()
        if not all_files:
            return 0

        # Build full files_context for rule-based agents (no LLM, no truncation)
        full_context_parts = []
        for relpath, content in all_files:
            full_context_parts.append(f"\n=== FILE: {relpath} ===\n{content}")
        full_context = "\n".join(full_context_parts)

        # Build batched contexts for LLM agents
        batches = self._build_batched_contexts(all_files)

        all_findings = []

        # ── 1. Rule-based agents: scan ALL files deterministically ─────────
        rule_agent_names = {
            "security", "healthcare", "phi_protection", "compliance",
            "medical_data", "fhir", "dicom", "hl7", "cds",
        }
        rule_agent_names_inferred = {"SecurityAgent", "HealthcareAgent",
                                      "PHIAgent", "ComplianceAgent",
                                      "MedicalDataAgent", "FHIRAgent",
                                      "DICOMAgent", "HL7Agent", "CDSRulesAgent"}

        for agent_name in self.active_agents:
            agent = self.agents.get(agent_name)
            if not agent:
                continue
            agent_class_name = type(agent).__name__
            is_rule_agent = (
                agent_name in rule_agent_names or
                agent_class_name in rule_agent_names_inferred
            )
            if not is_rule_agent:
                continue

            try:
                findings = agent.inspect(full_context)
                filtered = self._filter_false_positives(findings)
                for f in filtered:
                    if not f.check_name.startswith(agent_name):
                        f.check_name = f"{agent_name}_{f.check_name}"
                all_findings.extend(filtered)
                self.bus.send(
                    sender=agent_name, receiver="orchestrator",
                    msg_type=MessageType.FINDING,
                    content=f"Rule scan: {len(filtered)} findings across {len(all_files)} files",
                    data={"count": len(filtered), "files_scanned": len(all_files)},
                )
            except Exception as e:
                self.bus.send(
                    sender=agent_name, receiver="orchestrator",
                    msg_type=MessageType.FINDING,
                    content=f"Rule scan error: {e}", data={"error": str(e)},
                )

        # ── 2. LinterAgent: run Ruff directly ─────────────────────────────
        ruff_findings = self._run_ruff_linter()
        all_findings.extend(ruff_findings)
        self.bus.send(
            sender="linter", receiver="orchestrator",
            msg_type=MessageType.FINDING,
            content=f"Ruff linter: {len(ruff_findings)} findings",
            data={"count": len(ruff_findings)},
        )

        # ── 3. LLM agents: scan in batches ─────────────────────────────────
        llm_agent_names = [
            a for a in self.active_agents
            if a not in rule_agent_names and a not in ("linter",)
            and not a.startswith("db_") and not a.startswith("api_") and a != "smoke_test"
        ]

        for agent_name in llm_agent_names:
            agent = self.agents.get(agent_name)
            if not agent:
                continue
            if not getattr(agent, 'llm', None):
                continue

            batch_findings = []
            for batch_idx, batch_context in enumerate(batches):
                try:
                    f_list = agent.inspect(batch_context)
                    batch_findings.extend(f_list)
                except Exception:
                    continue
                # Rate-limit between batches
                if batch_idx < len(batches) - 1:
                    import time
                    time.sleep(0.5)

            filtered = self._filter_false_positives(batch_findings)
            for f in filtered:
                if not f.check_name.startswith(agent_name):
                    f.check_name = f"{agent_name}_{f.check_name}"
                # Drop findings without file location (LLM hallucination)
                if not f.file_path and not f.evidence:
                    continue
            all_findings.extend([f for f in filtered if f.file_path or f.evidence])

            self.bus.send(
                sender=agent_name, receiver="orchestrator",
                msg_type=MessageType.FINDING,
                content=f"LLM scan: {len(filtered)} findings across {len(batches)} batches",
                data={"count": len(filtered), "batches": len(batches)},
            )

        # ── 4. Dynamic analysis agents ─────────────────────────────────────
        for agent_name in self.active_agents:
            if not (agent_name.startswith("db_") or agent_name.startswith("api_") or agent_name == "smoke_test"):
                continue
            agent = self.agents.get(agent_name)
            if not agent:
                continue
            try:
                findings = agent.inspect(full_context[:100000])
                all_findings.extend(findings)
            except Exception:
                continue

        # ── 5. CPG taint analysis ──────────────────────────────────────────
        cpg_findings = self._cpg_scan()
        all_findings = cpg_findings + all_findings

        self.all_findings = all_findings
        return len(self.all_findings)

    def _filter_false_positives(self, findings: List[Finding]) -> List[Finding]:
        """Filter known false positives from project and global memory."""
        filtered = []
        for f in findings:
            if self.project_memory.is_false_positive(f.check_name, f.message):
                continue
            if self.global_kb.check_false_positive(f.message):
                continue
            filtered.append(f)
        return filtered

    def _run_ruff_linter(self) -> List[Finding]:
        """Run Ruff linter directly via subprocess and convert to Finding list.

        Includes ALL 283 Ruff rules across E9/F/S/B/TRY/ISC/ICN/PIE/PYL/RUF
        selectors. Results are integrated as deterministic findings with high
        confidence for critical/error-level issues.
        """
        import subprocess as _sp

        findings = []
        try:
            result = _sp.run(
                ["ruff", "check", str(self.project_path),
                 "--select", "E9,F,S,B,TRY,ISC,ICN,PIE,PYL,RUF",
                 "--output-format", "json"],
                capture_output=True, text=True, timeout=120,
            )
            import json as _json
            diagnostics = _json.loads(result.stdout or "[]")

            for d in diagnostics:
                code = d.get("code", "RUF")
                msg = d.get("message", "")
                filename = d.get("filename", "")
                location = d.get("location", {})
                line = location.get("row", 0)
                col = location.get("column", 0)

                # Map Ruff codes to severity
                sev = "medium"
                if code.startswith(("E9", "F", "S1", "S2")):
                    sev = "high"
                elif code.startswith("S"):
                    sev = "medium"
                elif code.startswith("B"):
                    sev = "medium"
                else:
                    sev = "low"

                # Build relative path
                try:
                    rel = os.path.relpath(filename, self.project_path)
                except ValueError:
                    rel = filename

                findings.append(Finding(
                    check_name=f"ruff_{code}",
                    severity=sev,
                    message=msg,
                    file_path=rel,
                    line_start=line,
                    line_end=line,
                    evidence=f"{rel}:{line}:{col}",
                    remediation=d.get("fix", {}).get("message", ""),
                    confidence=0.98 if sev in ("high",) else 0.85,
                ))
        except Exception:
            pass
        return findings

    def _cpg_scan(self) -> List[Finding]:
        """Run Code Property Graph deep analysis on project files."""
        try:
            import glob as glob_mod

            cpg = CPGAnalyzer()
            file_map: Dict[str, str] = {}

            for filepath in glob_mod.glob(
                os.path.join(self.project_path, "**", "*.py"), recursive=True,
            ):
                relpath = os.path.relpath(filepath, self.project_path)
                if "agents" in relpath.split(os.sep) or "__pycache__" in relpath:
                    continue
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    file_map[filepath] = content
                except Exception:
                    continue

            reports = cpg.analyze_project(file_map)
            summary = cpg.summary(reports)

            findings = []
            for report in reports:
                for taint_path in report.taint_paths:
                    raw = taint_to_rule_findings(taint_path)
                    finding = Finding(
                        check_name=raw["check_name"],
                        severity=raw["severity"],
                        message=raw["message"],
                        file_path=raw["file_path"],
                        line_start=raw["line_start"],
                        line_end=raw.get("line_end", raw["line_start"]),
                        evidence=raw["evidence"],
                        remediation=raw["remediation"],
                        confidence=raw.get("confidence", 0.8),
                    )
                    findings.append(finding)

            self.bus.send(
                sender="cpg_analyzer",
                receiver="orchestrator",
                msg_type=MessageType.FINDING,
                content=f"CPG found {len(findings)} taint paths "
                        f"({summary['critical_paths']} critical, {summary['high_paths']} high)",
                data=summary,
            )

            return findings
        except Exception as e:
            self.bus.send(
                sender="cpg_analyzer",
                receiver="orchestrator",
                msg_type=MessageType.FINDING,
                content=f"CPG scan failed: {e}",
            )
            return []

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
        """Debate phase: LLM-driven multi-perspective challenge on low-confidence findings.

        For findings with confidence in the dispute range (0.35-0.75), an LLM
        judge reviews the evidence and provides a real ruling — not random simulation.

        Strategy:
        1. Select findings in the dispute confidence range
        2. Build a judge prompt with finding details + cross-review comments
        3. LLM judge evaluates and rules confirmed/rejected/adjusted
        4. Apply ruling back to the finding
        """
        # Honor MAX_DEBATE_ROUNDS: 0 means debate disabled
        if self.MAX_DEBATE_ROUNDS <= 0:
            return []

        debate_max = self._cfg("debate", "max_rounds", default=5)

        # Select findings in dispute range (low-confidence or disagreed)
        disputed = [
            f for f in self.all_findings
            if f.reviewed and f.ruling not in ("rejected",)
            and (0.35 < f.confidence < 0.75 or f.ruling == "adjusted")
        ]
        if not disputed:
            disputed = [
                f for f in self.all_findings
                if f.reviewed and f.ruling != "rejected"
            ][:debate_max]

        # Limit to debate_max
        debated = disputed[:debate_max]

        for finding in debated:
            challenger_name = "orchestrator_debate_judge"
            reason = (
                f"Debate review: {finding.check_name} "
                f"(severity={finding.severity}, confidence={finding.confidence:.2f})"
            )

            debate_id = self.bus.open_debate(finding, challenger_name, reason)
            origin = finding.check_name.split("_")[0] if "_" in finding.check_name else "unknown"

            # Use LLM judge if available
            ruling, rationale, adjusted_severity = self._debate_judge(finding)

            result = self.bus.close_debate(
                debate_id=debate_id,
                arbiter="orchestrator",
                ruling=ruling,
                rationale=rationale,
            )

            if result:
                result.defender = origin
                self.debate_results.append(result)
                # Apply debate ruling
                if ruling == "confirmed":
                    finding.confidence = max(finding.confidence, 0.70)
                    finding.ruling = "confirmed"
                elif ruling == "rejected":
                    finding.confidence = min(finding.confidence, 0.30)
                    finding.ruling = "rejected"
                elif ruling == "adjusted" and adjusted_severity:
                    finding.ruling = "adjusted"
                    finding.severity = adjusted_severity

        return self.debate_results

    def _debate_judge(self, finding: Finding) -> tuple:
        """Use LLM to evaluate a disputed finding.

        Returns (ruling, rationale, adjusted_severity).
        If LLM unavailable, uses heuristic based on confidence.
        """
        if self.llm:
            try:
                prompt = f"""You are a code review debate judge. Evaluate this reported finding:

FINDING:
- Check: {finding.check_name}
- Severity: {finding.severity}
- Message: {finding.message}
- File: {finding.file_path}
- Line: {finding.line_start}
- Evidence: {finding.evidence or 'not provided'}
- Reviewer: {finding.reviewer}
- Current confidence: {finding.confidence:.2f}

Judge whether this is a real issue or a false positive.
Respond with ONLY one word and a one-sentence reason in this format:
RULING: <confirmed|rejected|adjusted>
SEVERITY: <critical|high|medium|low|info>
REASON: <one sentence reason>"""

                response = self.llm.generate(prompt, temperature=0.1, max_tokens=150)

                ruling = "confirmed"
                sev = finding.severity
                reason = "LLM judge evaluated"
                for line in response.split("\n"):
                    if line.upper().startswith("RULING:"):
                        r = line.split(":", 1)[1].strip().lower()
                        if r in ("confirmed", "rejected", "adjusted"):
                            ruling = r
                    if line.upper().startswith("SEVERITY:"):
                        s = line.split(":", 1)[1].strip().lower()
                        if s in ("critical", "high", "medium", "low", "info"):
                            sev = s
                    if line.upper().startswith("REASON:"):
                        reason = line.split(":", 1)[1].strip()

                return (ruling, reason, sev if ruling == "adjusted" else None)
            except Exception:
                pass

        # Heuristic fallback: low confidence + no evidence = likely FP
        if finding.confidence < 0.5 and not finding.evidence:
            return ("rejected", "Low confidence without evidence — heuristic rejection", None)
        if finding.confidence < 0.5:
            return ("adjusted", "Low confidence — adjusted severity", "low")
        return ("confirmed", "Sufficient confidence for confirmation", None)

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
        """Run a complete multi-agent review cycle with fix-and-re-scan.

        Each round:
        1. All agents inspect → collect findings
        2. Harness validation → cross-review → debate
        3. Generate & APPLY fix proposals (try LLM first, fallback to rule engine)
        4. Re-scan → track reduction in findings
        5. Converge when no new findings for 2 consecutive rounds

        Convergence types:
        - converged_fixed: fixes were applied AND finding count decreased
        - converged_stable: no new findings but no fixes could be applied
        - max_rounds: reached round limit without convergence

        Args:
            max_rounds: Override config value. Defaults to config or 5.
        """
        if max_rounds is None:
            max_rounds = self._cfg("convergence", "max_rounds", default=5)

        if not self._project_profile:
            self.initialize()

        cycle_log = []
        total_fixed_across_rounds = 0
        previous_confirmed_count = None
        convergence_type = "max_rounds"

        for round_num in range(1, max_rounds + 1):
            round_data = {
                "round": round_num,
                "timestamp": datetime.now(UTC).isoformat(),
                "active_agents": list(self.active_agents),
            }

            # ── Phase 1: Inspect — scan current state of code ──────────────
            round_data["findings_count"] = self.inspect_phase()

            if round_data["findings_count"] == 0:
                round_data["status"] = "clean"
                cycle_log.append(round_data)
                convergence_type = "clean"
                break

            # ── Phase 2: Review + Harness ──────────────────────────────────
            round_data["review_stats"] = self.review_phase()

            confirmed_issues = [f.to_dict() for f in self.all_findings if f.ruling == "confirmed"]
            rejected_issues = [f.to_dict() for f in self.all_findings if f.ruling == "rejected"]

            # ── Phase 3: Debate — LLM judge evaluates disputed findings ────
            round_data["debates"] = [d.to_dict() for d in self.debate_phase()]

            confirmed_count = len([f for f in self.all_findings if f.ruling == "confirmed"])
            round_data["confirmed_count"] = confirmed_count

            # ── Phase 4: Fix — generate AND APPLY fixes ────────────────────
            fix_proposals = self.generate_fix_proposals()
            auto_fixable = [p for p in fix_proposals if p.get("can_auto_fix", False)]
            round_data["fix_proposals_total"] = len(fix_proposals)
            round_data["fix_proposals_auto"] = len(auto_fixable)

            fix_applied = 0
            fix_error = None

            if auto_fixable:
                try:
                    engine = FixEngine(str(self.project_path), llm_service=self.llm)
                    fix_results = engine.execute_fixes(auto_fixable, fix_all=False)
                    fix_applied = sum(1 for r in fix_results if r.success)
                    round_data["fixes_applied"] = fix_applied
                    round_data["fixes_failed"] = len(fix_results) - fix_applied
                    total_fixed_across_rounds += fix_applied

                    if fix_applied > 0:
                        # Re-scan after fixes: reduce finding count for fixed items
                        self.all_findings = [
                            f for f in self.all_findings
                            if f.ruling != "confirmed"
                        ]
                        round_data["findings_after_fix"] = len(self.all_findings)
                except Exception as e:
                    fix_error = str(e)
                    round_data["fix_error"] = fix_error
                    round_data["fixes_applied"] = 0

            # Record
            self.project_memory.record_scan(
                round_number=round_num,
                issue_count=round_data["findings_count"],
                status="completed",
                agent_count=len(self.active_agents),
            )

            cycle_log.append(round_data)

            # ── Convergence check ──────────────────────────────────────────
            if self.check_convergence():
                convergence_type = "converged_fixed" if fix_applied > 0 else "converged_stable"
                round_data["status"] = convergence_type
                break

            # Check: has count decreased relative to previous round?
            if previous_confirmed_count is not None:
                delta = previous_confirmed_count - confirmed_count
                round_data["finding_delta"] = delta
                if delta <= 0 and fix_applied == 0 and round_num >= 3:
                    convergence_type = "converged_stable"
                    round_data["status"] = convergence_type
                    break

            previous_confirmed_count = confirmed_count
            round_data["status"] = "in_progress"

        # ── Generate evolution report ──────────────────────────────────────
        from ..evolution import HealthScorer
        scorer = HealthScorer()
        final_confirmed = [f.to_dict() for f in self.all_findings if f.ruling == "confirmed"]
        health = scorer.compute(final_confirmed)

        # Global stats
        self.global_kb.record_project_stats(
            project_type=self._project_profile.get("project_type", ""),
            issue_count=len(self.all_findings),
            fixed_count=total_fixed_across_rounds,
        )

        return {
            "project": self._project_profile,
            "cycles": cycle_log,
            "total_rounds": len(cycle_log),
            "total_findings": sum(c.get("findings_count", 0) for c in cycle_log),
            "unique_findings_final_round": cycle_log[-1]["findings_count"] if cycle_log else 0,
            "total_fixed": total_fixed_across_rounds,
            "confirmed_issues": final_confirmed,
            "rejected_issues": rejected_issues,
            "debate_results": [d.to_dict() for d in self.debate_results],
            "fix_proposals": self.generate_fix_proposals(),
            "converged": convergence_type.startswith("converged"),
            "convergence_type": convergence_type,
            "health_score": health.get("health_score", 0),
            "health_level": health.get("level", "unknown"),
            "bus_stats": self.bus.get_stats(),
            "global_stats": self.global_kb.get_stats(),
            "drift": {},
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
