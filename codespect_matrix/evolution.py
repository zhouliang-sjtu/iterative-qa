"""Evolution engine — health scoring, technical debt, architecture analysis.

Core capabilities:
- Code Health Score: weighted finding severity → 0-100 normalized
- Technical Debt Index: TODO/FIXME/HACK density + complexity factors
- Architecture Health: import graph analysis, module coupling, God module detection
- Evolution Trend: baseline comparison, improvement/degradation tracking
"""

from __future__ import annotations

import os
import ast
import json
import hashlib
import subprocess
from datetime import datetime, UTC
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Set, Tuple


# ── Severity weight table ─────────────────────────────────────────────────────

SEVERITY_WEIGHTS = {
    "critical": 100,
    "high": 50,
    "medium": 15,
    "low": 3,
    "info": 0,
}


# ── Health Scoring ────────────────────────────────────────────────────────────

class HealthScorer:
    """Compute a 0-100 code health score from agent findings.

    Formula:
        raw_score = sum(severity_weight * count) per severity level
        max_score = sum(severity_weight * 10)  # 10 findings/severity as baseline
        health = max(0, 100 - (raw_score / max_score) * 100)

    Interpretation:
        90-100: Excellent — production-ready
        70-89:  Good — minor improvements needed
        50-69:  Fair — moderate technical debt
        30-49:  Poor — significant issues
        0-29:   Critical — requires immediate attention
    """

    def compute(self, findings: List[Dict]) -> Dict[str, Any]:
        """Compute health score from a list of finding dicts."""
        counts = Counter()
        for f in findings:
            sev = f.get("severity", "low")
            counts[sev] += 1

        raw_score = 0
        max_score = 0
        for sev, weight in SEVERITY_WEIGHTS.items():
            raw_score += weight * counts.get(sev, 0)
            max_score += weight * 10  # baseline: 10 findings per severity

        health = max(0.0, min(100.0, 100.0 - (raw_score / max(max_score, 1)) * 100.0))

        level = (
            "excellent" if health >= 90 else
            "good" if health >= 70 else
            "fair" if health >= 50 else
            "poor" if health >= 30 else
            "critical"
        )

        return {
            "health_score": round(health, 1),
            "level": level,
            "raw_penalty": raw_score,
            "severity_counts": dict(counts),
            "total_findings": len(findings),
        }


# ── Technical Debt ────────────────────────────────────────────────────────────

class TechDebtAnalyzer:
    """Analyze technical debt from code markers and complexity.

    Scans for:
    - TODO / FIXME / HACK / XXX / BUG markers
    - Comment-to-code ratio
    - Long files (>500 lines)
    - Deeply nested functions
    """

    MARKER_PATTERNS = ["TODO", "FIXME", "HACK", "XXX", "BUG", "WORKAROUND"]

    def analyze(self, project_path: str) -> Dict[str, Any]:
        """Scan project for technical debt indicators."""
        markers = []
        total_lines = 0
        total_comment_lines = 0
        file_stats = []

        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in
                       ('__pycache__', 'node_modules', 'venv', '.venv', 'dist', 'build')]

            for file in files:
                if not file.endswith('.py'):
                    continue

                filepath = os.path.join(root, file)
                relpath = os.path.relpath(filepath, project_path)

                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                except Exception:
                    continue

                file_lines = len(lines)
                total_lines += file_lines
                comment_lines = 0
                file_markers = []

                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                        comment_lines += 1
                    for marker in self.MARKER_PATTERNS:
                        if marker in stripped and stripped.startswith('#'):
                            file_markers.append({
                                "marker": marker,
                                "line": i,
                                "content": stripped[:120],
                            })

                total_comment_lines += comment_lines

                if file_markers or file_lines > 500:
                    file_stats.append({
                        "file": relpath,
                        "lines": file_lines,
                        "comment_ratio": round(
                            comment_lines / max(file_lines, 1) * 100, 1,
                        ),
                        "markers": file_markers,
                        "overly_long": file_lines > 500,
                    })
                    markers.extend(file_markers)

        # Debt index calculation
        marker_penalty = len(markers) * 5
        large_file_penalty = sum(1 for f in file_stats if f["overly_long"]) * 10
        comment_penalty = max(
            0, 15 - round(total_comment_lines / max(total_lines, 1) * 100),
        ) * 2  # penalty if < 15% comments

        debt_index = min(100, marker_penalty + large_file_penalty + comment_penalty)
        level = "low" if debt_index < 20 else "moderate" if debt_index < 50 else "high" if debt_index < 80 else "critical"

        return {
            "debt_index": debt_index,
            "level": level,
            "marker_count": len(markers),
            "markers": markers,
            "large_files": [f for f in file_stats if f["overly_long"]],
            "file_details": file_stats[:30],
            "total_lines": total_lines,
            "comment_ratio": round(
                total_comment_lines / max(total_lines, 1) * 100, 1,
            ),
        }


# ── Architecture Analysis ─────────────────────────────────────────────────────

class ArchitectureAnalyzer:
    """Analyze project architecture: imports, coupling, module health.

    Builds a lightweight import graph and computes:
    - Fan-in / fan-out per module
    - Cyclic dependency detection (via DFS)
    - God module detection (>1000 lines + high fan-out)
    """

    def analyze(self, project_path: str) -> Dict[str, Any]:
        """Analyze architecture of a Python project."""
        imports = defaultdict(set)      # module → set of imported modules
        reverse_imports = defaultdict(set)  # module → set of modules that import it
        module_sizes = {}

        for root, dirs, files in os.walk(project_path):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in
                       ('__pycache__', 'node_modules', 'venv', '.venv', 'dist', 'build')]

            for file in files:
                if not file.endswith('.py'):
                    continue

                filepath = os.path.join(root, file)
                relpath = os.path.relpath(filepath, project_path)
                module_name = relpath.replace(os.sep, '.').replace('.py', '')

                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        source = f.read()
                    module_sizes[module_name] = len(source.splitlines())

                    tree = ast.parse(source)
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                imports[module_name].add(alias.name.split('.')[0])
                        elif isinstance(node, ast.ImportFrom):
                            if node.module:
                                imports[module_name].add(node.module.split('.')[0])
                except Exception:
                    continue

        # Build reverse map
        for mod, deps in imports.items():
            for dep in deps:
                reverse_imports[dep].add(mod)

        # Compute coupling
        coupling = {}
        for mod in imports:
            fan_out = len(imports[mod])
            fan_in = len(reverse_imports.get(mod, set()))
            coupling[mod] = {
                "fan_in": fan_in,
                "fan_out": fan_out,
                "coupling_score": min(100, (fan_in + fan_out) * 10),
                "lines": module_sizes.get(mod, 0),
            }

        # Detect cycles
        cycles = self._detect_cycles(imports)

        # God modules
        god_modules = [
            {
                "module": mod,
                "lines": coupling[mod]["lines"],
                "fan_out": coupling[mod]["fan_out"],
                "fan_in": coupling[mod]["fan_in"],
            }
            for mod, info in coupling.items()
            if info["lines"] > 1000 or info["fan_out"] > 15
        ]

        # Overall architecture health
        avg_coupling = (
            sum(c["coupling_score"] for c in coupling.values()) / max(len(coupling), 1)
        )
        health = max(0.0, 100.0 - avg_coupling - len(cycles) * 10)

        return {
            "architecture_health": round(health, 1),
            "level": self._health_level(health),
            "module_count": len(coupling),
            "avg_coupling_score": round(avg_coupling, 1),
            "god_modules": god_modules,
            "cycles": cycles,
            "top_coupled": sorted(
                coupling.items(),
                key=lambda x: x[1]["coupling_score"],
                reverse=True,
            )[:10],
        }

    def _detect_cycles(self, imports: Dict[str, Set[str]]) -> List[List[str]]:
        """Detect cycles in import graph via DFS."""
        cycles = []
        visited = set()
        stack = []

        def dfs(node, path):
            if node in path:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            path.append(node)
            for neighbor in imports.get(node, set()):
                dfs(neighbor, path[:])
            path.pop()

        # Only check project-internal modules
        project_modules = set(imports.keys())
        for mod in list(project_modules)[:50]:  # limit for performance
            dfs(mod, [])

        # Deduplicate: keep unique cycles
        unique = []
        seen = set()
        for cycle in cycles:
            key = tuple(sorted(cycle))
            if key not in seen:
                seen.add(key)
                unique.append(cycle)
        return unique

    @staticmethod
    def _health_level(score: float) -> str:
        if score >= 80:
            return "clean"
        if score >= 60:
            return "moderate"
        if score >= 40:
            return "tangled"
        return "critical"


# ── Test Coverage Estimator ──────────────────────────────────────────────────

class TestCoverageEstimator:
    """Estimate test coverage via pytest --cov when available."""

    def estimate(self, project_path: str) -> Dict[str, Any]:
        """Run pytest --cov and parse results."""
        # Try reading existing coverage.json first
        cov_path = os.path.join(project_path, "coverage.json")
        if os.path.exists(cov_path):
            try:
                with open(cov_path, 'r') as f:
                    data = json.load(f)
                totals = data.get("totals", {})
                pct = totals.get("percent_covered", 0)
                return {
                    "has_coverage": True,
                    "percent_covered": round(pct, 1),
                    "covered_lines": totals.get("covered_lines", 0),
                    "total_lines": totals.get("num_statements", 0),
                    "level": self._coverage_level(pct),
                }
            except Exception:
                pass

        # Try running pytest --cov
        try:
            result = subprocess.run(
                ["pytest", "--cov=" + project_path, "--cov-report=json",
                 "--cov-report=term", "-q"],
                cwd=project_path, capture_output=True, text=True, timeout=120,
            )
            if os.path.exists(cov_path):
                with open(cov_path, 'r') as f:
                    data = json.load(f)
                totals = data.get("totals", {})
                return {
                    "has_coverage": True,
                    "percent_covered": round(totals.get("percent_covered", 0), 1),
                    "covered_lines": totals.get("covered_lines", 0),
                    "total_lines": totals.get("num_statements", 0),
                    "level": self._coverage_level(totals.get("percent_covered", 0)),
                }
        except Exception:
            pass

        # Fallback: count test files
        test_count = 0
        for root, dirs, files in os.walk(project_path):
            for file in files:
                if file.startswith("test_") or file.endswith("_test.py"):
                    test_count += 1

        return {
            "has_coverage": False,
            "percent_covered": 0,
            "test_files_found": test_count,
            "level": "unknown",
            "note": "Run `pip install pytest-cov` for accurate coverage",
        }

    @staticmethod
    def _coverage_level(pct: float) -> str:
        if pct >= 80:
            return "good"
        if pct >= 50:
            return "moderate"
        if pct > 0:
            return "low"
        return "none"


# ── Evolution Report Generator ────────────────────────────────────────────────

class EvolutionReporter:
    """Generate a comprehensive evolution report combining all analyses."""

    def __init__(self, project_path: str):
        self.project_path = project_path
        self.health = HealthScorer()
        self.debt = TechDebtAnalyzer()
        self.arch = ArchitectureAnalyzer()
        self.coverage = TestCoverageEstimator()

    def full_report(
        self,
        agent_findings: List[Dict],
        baseline_data: Dict = None,
    ) -> Dict[str, Any]:
        """Generate a full evolution analysis report."""
        report = {
            "project": os.path.basename(self.project_path),
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "1.0.0",
        }

        # 1. Health Score
        report["health"] = self.health.compute(agent_findings)

        # 2. Technical Debt
        report["technical_debt"] = self.debt.analyze(self.project_path)

        # 3. Architecture
        report["architecture"] = self.arch.analyze(self.project_path)

        # 4. Test Coverage
        report["test_coverage"] = self.coverage.estimate(self.project_path)

        # 5. Overall score (weighted composite)
        health = report["health"]["health_score"]
        arch = report["architecture"]["architecture_health"]
        debt = 100 - report["technical_debt"]["debt_index"]
        cov = report["test_coverage"].get("percent_covered", 0)

        overall = round(health * 0.4 + arch * 0.25 + debt * 0.25 + cov * 0.1, 1)
        report["overall_score"] = overall
        report["overall_level"] = self._overall_level(overall)

        # 6. Baseline comparison
        if baseline_data:
            report["delta"] = self._compute_delta(report, baseline_data)

        # 7. Improvement roadmap
        report["roadmap"] = self._generate_roadmap(report)

        return report

    def _compute_delta(self, current: Dict, baseline: Dict) -> Dict:
        """Compute delta between current and baseline."""
        h_now = current["health"]["health_score"]
        h_before = baseline.get("health", {}).get("health_score", h_now)
        d_now = current["technical_debt"]["debt_index"]
        d_before = baseline.get("technical_debt", {}).get("debt_index", d_now)
        findings_now = current["health"]["total_findings"]
        findings_before = baseline.get("health", {}).get("total_findings", findings_now)

        trend = (
            "improving" if h_now > h_before and d_now < d_before else
            "degrading" if h_now < h_before and d_now > d_before else
            "stable"
        )

        return {
            "trend": trend,
            "health_delta": round(h_now - h_before, 1),
            "debt_delta": round(d_now - d_before, 1),
            "findings_delta": findings_now - findings_before,
        }

    def _overall_level(self, score: float) -> str:
        if score >= 85:
            return "excellent"
        if score >= 70:
            return "good"
        if score >= 50:
            return "fair"
        if score >= 30:
            return "needs_work"
        return "critical"

    def _generate_roadmap(self, report: Dict) -> List[Dict]:
        """Generate prioritized improvement roadmap."""
        items = []

        h = report["health"]
        d = report["technical_debt"]
        a = report["architecture"]
        c = report["test_coverage"]

        if h["health_score"] < 70:
            items.append({
                "priority": "P0",
                "category": "quality",
                "action": "Fix critical and high-severity findings",
                "rationale": f"Health score {h['health_score']} — {h['severity_counts']}",
                "effort": "varies",
            })

        if d["debt_index"] > 30 and d["marker_count"] > 0:
            items.append({
                "priority": "P1",
                "category": "technical_debt",
                "action": f"Resolve {d['marker_count']} TODO/FIXME/HACK markers",
                "rationale": f"Debt index {d['debt_index']}/100",
                "effort": f"{d['marker_count'] * 0.5:.0f}h estimated",
            })

        if d["debt_index"] > 30 and len(d.get("large_files", [])) > 0:
            large = [f["file"] for f in d["large_files"][:3]]
            items.append({
                "priority": "P2",
                "category": "technical_debt",
                "action": f"Split {len(d['large_files'])} oversized files (>500 lines)",
                "rationale": f"Large files: {', '.join(large)}",
                "effort": f"{len(d['large_files']) * 2}h estimated",
            })

        if a["god_modules"]:
            items.append({
                "priority": "P1",
                "category": "architecture",
                "action": f"Refactor {len(a['god_modules'])} God modules",
                "rationale": ", ".join(m["module"] for m in a["god_modules"][:3]),
                "effort": "2-4h per module",
            })

        if a["cycles"]:
            items.append({
                "priority": "P2",
                "category": "architecture",
                "action": f"Break {len(a['cycles'])} import cycles",
                "rationale": "Cyclic dependencies hurt maintainability",
                "effort": "1-2h per cycle",
            })

        if c.get("percent_covered", 0) < 50:
            items.append({
                "priority": "P2",
                "category": "testing",
                "action": "Increase test coverage to 50%+",
                "rationale": f"Current coverage: {c.get('percent_covered', 0)}%",
                "effort": "depends on project size",
            })

        return items


# ── Baseline persistence ──────────────────────────────────────────────────────

class EvolutionBaseline:
    """Save and load evolution baselines for trend tracking."""

    BASELINE_FILE = ".codespect_matrix_evolution_baseline.json"

    def __init__(self, project_path: str):
        self.path = os.path.join(project_path, self.BASELINE_FILE)

    def save(self, report: Dict):
        """Save current evolution report as baseline."""
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    def load(self) -> Optional[Dict]:
        """Load a previous baseline."""
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def diff(self, current: Dict) -> Optional[Dict]:
        """Compare current report against baseline."""
        previous = self.load()
        if not previous:
            return None

        h_now = current["health"]["health_score"]
        h_before = previous.get("health", {}).get("health_score", h_now)
        d_now = current["technical_debt"]["debt_index"]
        d_before = previous.get("technical_debt", {}).get("debt_index", d_now)

        trend = (
            "improving" if h_now > h_before and d_now < d_before else
            "degrading" if h_now < h_before and d_now > d_before else
            "stable"
        )

        delta_summary = {
            "trend": trend,
            "health_now": round(h_now, 1),
            "health_before": round(h_before, 1),
            "health_delta": round(h_now - h_before, 1),
            "debt_now": d_now,
            "debt_before": d_before,
            "debt_delta": d_now - d_before,
        }

        # Compare finding counts
        if "health" in previous and "health" in current:
            prev_findings = previous["health"].get("total_findings", 0)
            curr_findings = current["health"].get("total_findings", 0)
            delta_summary["findings_delta"] = curr_findings - prev_findings

        return delta_summary
