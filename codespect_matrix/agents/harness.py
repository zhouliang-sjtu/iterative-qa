"""Harness Engineering Layer — constraint, verification, feedback, and recovery.

Harness Engineering (驾驭工程) 2026 paradigm:
  Agent = Model + Harness
  "Human Steer, Agent Execute"

This module provides the external constraint system that wraps the
multi-agent code review pipeline, ensuring:
1. Finding consistency (severity alignment, evidence quality)
2. Cross-phase verification (inspect → review → verify → output)
3. Feedback routing (review results feed back to improve agents)
4. Recovery handling (auto-retry, fallback on agent errors)
5. Drift detection (compare results against baseline)
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple
from enum import Enum
from collections import Counter


# ═══════════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════════

class HarnessAction(Enum):
    """Actions the harness can take on a finding."""
    PASS = "pass"           # Finding is valid, let through
    FLAG = "flag"           # Finding is suspicious, flag for review
    REJECT = "reject"       # Finding is invalid, remove
    ADJUST = "adjust"       # Adjust severity/confidence
    MERGE = "merge"         # Merge with similar finding
    RETRY = "retry"         # Retry the agent inspection


_ACTION_TO_FIELD = {
    HarnessAction.PASS: "passed",
    HarnessAction.FLAG: "flagged",
    HarnessAction.REJECT: "rejected",
    HarnessAction.ADJUST: "adjusted",
    HarnessAction.MERGE: "merged",
    HarnessAction.RETRY: "retried",
}


@dataclass
class HarnessVerdict:
    """Harness decision on a finding."""
    action: HarnessAction
    finding_id: str
    reason: str
    adjusted_severity: Optional[str] = None
    adjusted_confidence: Optional[float] = None
    merged_into: Optional[str] = None


@dataclass
class VerificationReport:
    """Result of a verification pass."""
    total: int
    passed: int
    flagged: int
    rejected: int
    adjusted: int
    merged: int
    retried: int
    details: List[HarnessVerdict] = field(default_factory=list)


@dataclass
class ConsistencyMetrics:
    """Consistency metrics across agent outputs."""
    severity_alignment: float      # 0-1: how aligned severity judgments are
    evidence_quality: float         # 0-1: how complete evidence is
    remediation_actionability: float  # 0-1: how actionable fixes are
    inter_agent_agreement: float    # 0-1: agreement rate between agents
    formatting_compliance: float    # 0-1: format compliance rate


@dataclass
class DriftReport:
    """Quality drift comparison between two runs."""
    new_issues: int
    resolved_issues: int
    severity_shift: Dict[str, int]   # e.g. {"critical": +3, "high": -2}
    new_categories: List[str]
    risk_score: float                 # 0-1, higher = more risky
    trend: str                        # "improving", "stable", "degrading"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Constraint System
# ═══════════════════════════════════════════════════════════════════════════════

# Severity hierarchy
SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}

# Known severity mappings for check categories (constrains agent outputs)
CATEGORY_SEVERITY_CONSTRAINTS = {
    # Medical mandatory
    "phi_leak":      ("critical", "high"),
    "hipaa":         ("critical", "high"),
    "fhir_security": ("critical", "high"),
    "dicom_security": ("critical", "high"),
    # Drug safety
    "drug_interaction": ("critical", "high"),
    "drug_allergy":     ("critical", "high"),
    "drug_pediatric":   ("critical",),
    # Device safety
    "device_failure":   ("critical",),
    "device_safety":    ("critical",),
    # EHR
    "ehr_immutable":   ("critical",),
    "ehr_signature":   ("high", "medium"),
    # Identity
    "patient_id":      ("critical", "high"),
    "deidentification": ("critical",),
    # Security
    "sql_injection":   ("critical",),
    "xss":             ("critical", "high"),
    "xxe":             ("critical",),
    "ssrf":            ("high",),
    "ldap_injection":  ("high",),
    "hardcoded":        ("high", "medium"),
    "weak_crypto":      ("high",),
    # Code quality
    "error_suppression": ("high",),
    "race_condition":    ("high",),
    "magic_number":      ("medium", "low"),
}

# Evidence quality requirements
MIN_EVIDENCE_LENGTH = 3  # minimum chars for evidence
MAX_EVIDENCE_LENGTH = 200  # maximum chars (trimmed)
SUSPICIOUS_EVIDENCE_PATTERNS = [
    r'^\s*$',               # empty/whitespace only
    r'^\s*#.*$',            # comment only
    r'^\s*pass\s*$',        # just 'pass'
    r'^\s*import\s',        # import line
    r'^\s*from\s.*import',  # from import
]


class ConstraintEnforcer:
    """Enforces structural and semantic constraints on agent findings.

    Constraints:
    - Severity must be in valid range
    - Evidence must be non-trivial
    - Confidence must be 0.0-1.0
    - Message must be descriptive (not just a category name)
    - Categories must match expected severity ranges
    """

    SEVERITY_VALUES = {"critical", "high", "medium", "low", "info"}

    def validate(self, findings: List[Dict]) -> Tuple[List[Dict], List[HarnessVerdict]]:
        """Validate all findings. Returns (valid_findings, verdicts)."""
        valid = []
        verdicts = []
        seen_hashes = set()  # dedup

        for f in findings:
            vid = f.get("check_name", "unknown")
            verdicts_for_f = []

            # 1. Severity constraint
            sev = f.get("severity", "medium")
            if sev not in self.SEVERITY_VALUES:
                f["severity"] = "medium"
                verdicts_for_f.append(HarnessVerdict(
                    HarnessAction.ADJUST, vid,
                    f"Invalid severity '{sev}' → adjusted to 'medium'",
                    adjusted_severity="medium",
                ))

            # 2. Category-severity constraint
            cat_sev = self._check_category_severity(vid, sev)
            if cat_sev:
                f["severity"] = cat_sev
                verdicts_for_f.append(HarnessVerdict(
                    HarnessAction.ADJUST, vid,
                    f"Severity adjusted per category constraint: '{sev}' → '{cat_sev}'",
                    adjusted_severity=cat_sev,
                ))

            # 3. Evidence quality check
            evidence = f.get("evidence", "")
            evidence_verdict = self._check_evidence(evidence)
            if evidence_verdict:
                verdicts_for_f.append(evidence_verdict)
                if evidence_verdict.action == HarnessAction.REJECT:
                    continue  # skip this finding

            # 4. Message quality
            msg = f.get("message", "")
            if len(msg) < 5 or msg == vid:
                f["_flag"] = "weak_message"
                verdicts_for_f.append(HarnessVerdict(
                    HarnessAction.FLAG, vid,
                    f"Weak message: '{msg[:50]}'",
                ))

            # 5. Confidence range
            conf = f.get("confidence", 1.0)
            if not isinstance(conf, (int, float)) or conf < 0.0 or conf > 1.0:
                f["confidence"] = 0.5
                verdicts_for_f.append(HarnessVerdict(
                    HarnessAction.ADJUST, vid,
                    f"Invalid confidence {conf} → adjusted to 0.5",
                    adjusted_confidence=0.5,
                ))

            # 6. Deduplication
            fhash = self._hash_finding(f)
            if fhash in seen_hashes:
                verdicts_for_f.append(HarnessVerdict(
                    HarnessAction.MERGE, vid,
                    "Duplicate finding merged",
                    merged_into="previous",
                ))
                continue
            seen_hashes.add(fhash)

            # 7. Remediation quality
            rem = f.get("remediation", "")
            if len(rem) < 10 or rem == "Fix this issue" or rem == "Fix this security issue":
                f["_flag"] = "weak_remediation"

            valid.append(f)
            verdicts.extend(verdicts_for_f)

        return valid, verdicts

    def _check_category_severity(self, check_name: str, severity: str) -> Optional[str]:
        """Check if severity matches category constraints. Returns corrected severity or None."""
        for category, allowed in CATEGORY_SEVERITY_CONSTRAINTS.items():
            if category in check_name.lower():
                if severity not in allowed:
                    return allowed[0]  # pick the highest allowed
        return None

    def _check_evidence(self, evidence: str) -> Optional[HarnessVerdict]:
        """Check evidence quality."""
        ev = evidence.strip()

        if len(ev) < MIN_EVIDENCE_LENGTH:
            return HarnessVerdict(HarnessAction.FLAG, "", "Evidence too short or empty")

        if len(ev) > MAX_EVIDENCE_LENGTH:
            return None  # trimmed, but ok

        for pattern in SUSPICIOUS_EVIDENCE_PATTERNS:
            if re.match(pattern, ev):
                return HarnessVerdict(HarnessAction.FLAG, "", f"Suspicious evidence: '{ev[:40]}'")

        return None

    def _hash_finding(self, f: Dict) -> str:
        """Create dedup hash from finding key fields."""
        key = f"{f.get('check_name','')}|{f.get('file_path','')}|{f.get('line_start',0)}"
        return hashlib.md5(key.encode()).hexdigest()[:12]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Verification Loop
# ═══════════════════════════════════════════════════════════════════════════════

class VerificationLoop:
    """Multi-round verification of findings.

    Verification stages:
    1. Self-consistency: Are findings from same agent internally consistent?
    2. Cross-agent: Do different agents agree on similar findings?
    3. Rule-based: Do findings violate any known false-positive patterns?
    4. Evidence-backed: Is each finding backed by solid evidence?
    """

    def verify(
        self,
        findings: List[Dict],
        rejected: List[Dict],
        agent_map: Dict[str, str],  # finding_id → agent_name
    ) -> VerificationReport:
        """Run full verification on findings.

        Args:
            findings: Confirmed findings
            rejected: Rejected findings (re-check for false negatives)
            agent_map: Which agent produced each finding

        Returns:
            VerificationReport with actions taken
        """
        details = []
        stats = {"passed": 0, "flagged": 0, "rejected": 0, "adjusted": 0, "merged": 0, "retried": 0}

        # Stage 1: Self-consistency per agent
        agent_findings: Dict[str, List[Dict]] = {}
        for f in findings:
            a = agent_map.get(f.get("check_name", ""), "unknown")
            agent_findings.setdefault(a, []).append(f)

        for agent, afs in agent_findings.items():
            v = self._check_self_consistency(agent, afs)
            details.extend(v)
            for d in v:
                field = _ACTION_TO_FIELD.get(d.action, "flagged")
                stats[field] = stats.get(field, 0) + 1

        # Stage 2: Cross-agent similarity (near-duplicate detection across agents)
        merged, merge_details = self._cross_agent_dedup(findings, agent_map)
        details.extend(merge_details)
        stats["merged"] += len(merge_details)

        # Stage 3: Rejected finding re-check (false negative prevention)
        recheck = self._recheck_rejected(rejected)
        details.extend(recheck)
        stats["retried"] += len(recheck)

        # Stage 4: Evidence consistency
        ev_details = self._evidence_consistency(findings)
        details.extend(ev_details)
        for d in ev_details:
            field = _ACTION_TO_FIELD.get(d.action, "flagged")
            stats[field] = stats.get(field, 0) + 1

        # Count passed
        passed_ids = {self._finding_id(f) for f in findings}
        flagged_ids = {d.finding_id for d in details if d.action == HarnessAction.FLAG}
        stats["passed"] = len(passed_ids - flagged_ids)

        return VerificationReport(
            total=len(findings),
            **stats,
            details=details,
        )

    def _check_self_consistency(
        self, agent: str, findings: List[Dict]
    ) -> List[HarnessVerdict]:
        """Check if one agent's findings are internally consistent."""
        verdicts = []

        # Check: same agent shouldn't give wildly different severities to similar issues
        sev_counts = Counter(f.get("severity", "medium") for f in findings)
        if len(sev_counts) > 3 and len(findings) > 5:
            # Potentially inconsistent severity assignment
            pass

        # Check: findings shouldn't all have identical messages
        msgs = [f.get("message", "") for f in findings]
        if len(set(msgs)) == 1 and len(msgs) > 2:
            verdicts.append(HarnessVerdict(
                HarnessAction.FLAG, agent,
                f"Agent '{agent}' produced {len(msgs)} findings with identical messages",
            ))

        return verdicts

    def _cross_agent_dedup(
        self, findings: List[Dict], agent_map: Dict[str, str]
    ) -> Tuple[List[Dict], List[HarnessVerdict]]:
        """Merge near-duplicate findings from different agents."""
        seen: Dict[str, str] = {}  # hash → finding_id
        merged = []
        details = []

        for f in findings:
            key = f"{f.get('file_path','')}|{f.get('line_start',0)}|{f.get('check_name','').split('_')[0]}"
            if key in seen:
                # Merge: keep the one with better evidence
                existing = seen[key]
                details.append(HarnessVerdict(
                    HarnessAction.MERGE,
                    f.get("check_name", ""),
                    f"Merged near-duplicate at {f.get('file_path','')}:{f.get('line_start',0)}",
                    merged_into=existing,
                ))
            else:
                seen[key] = f.get("check_name", "")
                merged.append(f)

        return merged, details

    def _recheck_rejected(self, rejected: List[Dict]) -> List[HarnessVerdict]:
        """Re-check rejected findings for false negatives."""
        verdicts = []
        for f in rejected:
            sev = f.get("severity", "medium")
            if sev in ("critical", "high"):
                verdicts.append(HarnessVerdict(
                    HarnessAction.RETRY, f.get("check_name", ""),
                    f"Critical/HIGH finding was rejected — re-inspect: {f.get('message', '')[:60]}",
                ))
        return verdicts

    def _evidence_consistency(self, findings: List[Dict]) -> List[HarnessVerdict]:
        """Check that findings with high severity have solid evidence."""
        verdicts = []
        for f in findings:
            sev = f.get("severity", "medium")
            evidence = f.get("evidence", "")
            if sev in ("critical", "high") and len(evidence.strip()) < 10:
                verdicts.append(HarnessVerdict(
                    HarnessAction.FLAG, f.get("check_name", ""),
                    f"{sev.upper()} finding with weak evidence: '{evidence[:40]}'",
                ))
        return verdicts

    @staticmethod
    def _finding_id(f: Dict) -> str:
        return f.get("check_name", "unknown")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Feedback Router
# ═══════════════════════════════════════════════════════════════════════════════

class FeedbackRouter:
    """Routes verification results back to improve future scans.

    Feedback channels:
    - Pattern learning: rejected findings → update known-FP database
    - Agent weight adjustment: high-FP agents → lower confidence
    - Rule refinement: unclear edges → suggest new rules
    """

    def __init__(self):
        self.feedback_history: List[Dict] = []
        self.agent_performance: Dict[str, Dict] = {}

    def record(self, phase: str, verdicts: List[HarnessVerdict], agent: str = ""):
        """Record harness verdicts for learning."""
        self.feedback_history.append({
            "phase": phase,
            "timestamp": time.time(),
            "agent": agent,
            "verdict_count": len(verdicts),
            "actions": Counter(v.action.value for v in verdicts),
        })

        # Update agent performance
        if agent:
            perf = self.agent_performance.setdefault(agent, {
                "total": 0, "flagged": 0, "rejected": 0, "adjusted": 0,
            })
            perf["total"] += len(verdicts)
            for v in verdicts:
                if v.action.value in perf:
                    perf[v.action.value] += 1

    def get_agent_reliability(self, agent: str) -> float:
        """Calculate agent reliability score 0-1."""
        perf = self.agent_performance.get(agent, {})
        total = perf.get("total", 0)
        if total == 0:
            return 1.0
        bad = perf.get("rejected", 0) + perf.get("flagged", 0) * 0.5 + perf.get("adjusted", 0) * 0.3
        return max(0.0, 1.0 - (bad / total))

    def get_feedback_summary(self) -> Dict:
        """Generate feedback summary for reporting."""
        total_v = sum(
            h["verdict_count"] for h in self.feedback_history
            if isinstance(h.get("verdict_count"), int)
        )
        return {
            "total_verdicts": total_v,
            "agent_performance": {
                a: self.get_agent_reliability(a)
                for a in self.agent_performance
            },
            "phase_stats": Counter(
                h["phase"] for h in self.feedback_history
            ),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Consistency Metrics Calculator
# ═══════════════════════════════════════════════════════════════════════════════

class ConsistencyCalculator:
    """Calculate inter-agent and intra-agent consistency metrics."""

    def compute(self, findings: List[Dict], agent_map: Dict[str, str]) -> ConsistencyMetrics:
        """Compute all consistency metrics."""
        return ConsistencyMetrics(
            severity_alignment=self._severity_alignment(findings, agent_map),
            evidence_quality=self._evidence_quality(findings),
            remediation_actionability=self._remediation_actionability(findings),
            inter_agent_agreement=self._inter_agent_agreement(findings, agent_map),
            formatting_compliance=self._formatting_compliance(findings),
        )

    def _severity_alignment(self, findings: List[Dict], agent_map: Dict[str, str]) -> float:
        """How consistently do agents assign severity to similar issues?"""
        if len(findings) < 2:
            return 1.0

        # Group similar findings (same file + nearby line)
        groups: Dict[str, List[str]] = {}
        for f in findings:
            key = f"{f.get('file_path','')}|{f.get('line_start',0)//10}"
            groups.setdefault(key, []).append(f.get("severity", "medium"))

        aligned = 0
        total_groups = 0
        for sevs in groups.values():
            if len(sevs) >= 2:
                total_groups += 1
                if len(set(sevs)) == 1:
                    aligned += 1

        return aligned / total_groups if total_groups > 0 else 1.0

    def _evidence_quality(self, findings: List[Dict]) -> float:
        """How many findings have good evidence?"""
        if not findings:
            return 1.0
        good = sum(1 for f in findings if len(f.get("evidence", "").strip()) >= 10)
        return good / len(findings)

    def _remediation_actionability(self, findings: List[Dict]) -> float:
        """How many findings have actionable remediation?"""
        if not findings:
            return 1.0

        weak_phrases = {"fix this", "improve", "be careful", "check this", "review"}
        actionable = 0
        for f in findings:
            rem = f.get("remediation", "").lower()
            if len(rem) >= 20 and not any(w in rem[:30] for w in weak_phrases):
                actionable += 1
        return actionable / len(findings)

    def _inter_agent_agreement(self, findings: List[Dict], agent_map: Dict[str, str]) -> float:
        """How often do different agents agree?"""
        # Approximate: check if findings at same location from different agents have same ruling
        loc_map: Dict[str, List[str]] = {}
        for f in findings:
            loc = f"{f.get('file_path','')}|{f.get('line_start',0)}"
            loc_map.setdefault(loc, []).append(f.get("ruling", "confirmed"))

        agreed = 0
        total = 0
        for rulings in loc_map.values():
            if len(rulings) >= 2:
                total += 1
                if len(set(rulings)) == 1:
                    agreed += 1

        return agreed / total if total > 0 else 1.0

    def _formatting_compliance(self, findings: List[Dict]) -> float:
        """How many findings follow output format rules?"""
        if not findings:
            return 1.0
        required = ["check_name", "severity", "message", "file_path", "line_start", "evidence"]
        compliant = sum(
            1 for f in findings
            if all(key in f and f[key] for key in required)
        )
        return compliant / len(findings)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Drift Detector
# ═══════════════════════════════════════════════════════════════════════════════

class DriftDetector:
    """Detects quality drift between baseline and current scan."""

    def __init__(self):
        self.baselines: Dict[str, Dict] = {}

    def set_baseline(self, project: str, findings: List[Dict]):
        """Store baseline scan results."""
        self.baselines[project] = {
            "timestamp": time.time(),
            "findings": findings,
            "severity_counts": Counter(f.get("severity", "medium") for f in findings),
            "category_counts": Counter(
                f.get("check_name", "").split("_")[0] for f in findings
            ),
            "total": len(findings),
        }

    def compare(self, project: str, current_findings: List[Dict]) -> DriftReport:
        """Compare current findings against baseline."""
        baseline = self.baselines.get(project)
        if not baseline:
            return DriftReport(
                new_issues=0, resolved_issues=0,
                severity_shift={}, new_categories=[],
                risk_score=0.0, trend="stable",
            )

        cur_sev = Counter(f.get("severity", "medium") for f in current_findings)
        cur_cat = Counter(f.get("check_name", "").split("_")[0] for f in current_findings)
        cur_total = len(current_findings)

        # Per-file baseline comparison
        baseline_hashes = self._file_hash_set(baseline["findings"])
        current_hashes = self._file_hash_set(current_findings)

        new_issues = len(current_hashes - baseline_hashes)
        resolved_issues = len(baseline_hashes - current_hashes)

        # Severity shift
        sev_shift = {}
        for sev in SEVERITY_ORDER:
            diff = cur_sev.get(sev, 0) - baseline["severity_counts"].get(sev, 0)
            if diff != 0:
                sev_shift[sev] = diff

        # New categories
        base_cats = set(baseline["category_counts"].keys())
        new_cats = [c for c in cur_cat if c not in base_cats]

        # Risk score
        risk = self._compute_risk(sev_shift, new_issues, resolved_issues, cur_total,
                                  baseline["total"])

        # Trend
        if risk > 0.6:
            trend = "degrading"
        elif risk < 0.3:
            trend = "improving"
        else:
            trend = "stable"

        return DriftReport(
            new_issues=new_issues,
            resolved_issues=resolved_issues,
            severity_shift=sev_shift,
            new_categories=new_cats,
            risk_score=risk,
            trend=trend,
        )

    def _file_hash_set(self, findings: List[Dict]) -> Set[str]:
        return {
            f"{f.get('file_path','')}|{f.get('line_start',0)}|{f.get('check_name','')[:20]}"
            for f in findings
        }

    def _compute_risk(self, sev_shift: Dict, new: int, resolved: int,
                      cur_total: int, base_total: int) -> float:
        """Compute risk score 0-1."""
        risk = 0.0

        # Weighted severity increase
        weights = {"critical": 0.4, "high": 0.3, "medium": 0.15, "low": 0.05}
        for sev, diff in sev_shift.items():
            if diff > 0:
                risk += weights.get(sev, 0.1) * min(diff / 10, 1.0)

        # New issues vs resolved
        if base_total > 0:
            net = new - resolved
            if net > 0:
                risk += 0.3 * min(net / base_total, 1.0)
            elif net < 0:
                risk -= 0.2  # bonus for reducing issues

        # Total growth
        if base_total > 0:
            growth = (cur_total - base_total) / base_total
            if growth > 0.2:
                risk += 0.3

        return max(0.0, min(1.0, risk))


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Harness Engine — integrates all components
# ═══════════════════════════════════════════════════════════════════════════════

class HarnessEngine:
    """Complete Harness Engineering layer for codespect-matrix.

    Usage:
        harness = HarnessEngine()
        harness.set_baseline("my_project", previous_findings)

        # After inspect phase
        valid, verdicts = harness.validate_after_inspect(findings)

        # After review phase
        verified = harness.verify_after_review(confirmed, rejected)

        # After debate phase
        drift = harness.detect_drift("my_project", final_findings)

        # Get report
        metrics = harness.compute_metrics(final_findings)
        summary = harness.get_harness_report()
    """

    def __init__(self):
        self.constraint = ConstraintEnforcer()
        self.verifier = VerificationLoop()
        self.feedback = FeedbackRouter()
        self.consistency = ConsistencyCalculator()
        self.drift = DriftDetector()

        self._agent_map: Dict[str, str] = {}
        self._phase_verdicts: Dict[str, List[HarnessVerdict]] = {}

    def set_baseline(self, project: str, findings: List[Dict]):
        """Register a baseline for drift detection."""
        self.drift.set_baseline(project, findings)

    def validate_after_inspect(
        self, findings: List[Dict], agent_name: str = ""
    ) -> Tuple[List[Dict], List[HarnessVerdict]]:
        """Validate findings right after agent inspection phase."""
        # Build agent map
        for f in findings:
            ck = f.get("check_name", "")
            self._agent_map[ck] = agent_name or ck.split("_")[0]

        valid, verdicts = self.constraint.validate(findings)
        self._phase_verdicts["inspect"] = verdicts
        self.feedback.record("inspect", verdicts, agent_name)
        return valid, verdicts

    def verify_after_review(
        self, confirmed: List[Dict], rejected: List[Dict]
    ) -> VerificationReport:
        """Verify findings after review phase."""
        report = self.verifier.verify(confirmed, rejected, self._agent_map)
        self._phase_verdicts["review"] = report.details
        self.feedback.record("review", report.details)
        return report

    def detect_drift(self, project: str, findings: List[Dict]) -> DriftReport:
        """Detect quality drift after a full scan."""
        return self.drift.compare(project, findings)

    def compute_metrics(self, findings: List[Dict]) -> ConsistencyMetrics:
        """Compute consistency metrics."""
        return self.consistency.compute(findings, self._agent_map)

    def get_harness_report(self) -> Dict:
        """Generate complete harness report."""
        metrics = None  # last computed
        return {
            "harness_version": "1.0.0",
            "paradigm": "Agent = Model + Harness",
            "phases": {
                phase: {
                    "total_verdicts": len(verdicts),
                    "actions": Counter(v.action.value for v in verdicts),
                }
                for phase, verdicts in self._phase_verdicts.items()
            },
            "feedback": self.feedback.get_feedback_summary(),
            "consistency": metrics.__dict__ if metrics else {},
            "drift": None,  # set externally
        }
