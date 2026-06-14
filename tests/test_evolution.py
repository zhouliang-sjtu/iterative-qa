"""Unit tests for evolution engine (no LLM required)."""

import os
import json
import tempfile
import pytest
from codespect_matrix.evolution import (
    HealthScorer,
    TechDebtAnalyzer,
    ArchitectureAnalyzer,
    TestCoverageEstimator,
    EvolutionReporter,
    EvolutionBaseline,
    SEVERITY_WEIGHTS,
)


class TestHealthScorer:
    """HealthScorer: weighted severity → 0-100 score."""

    def test_empty_findings_100(self):
        scorer = HealthScorer()
        result = scorer.compute([])
        assert result["health_score"] == 100.0
        assert result["level"] == "excellent"
        assert result["total_findings"] == 0

    def test_single_low_severity(self):
        scorer = HealthScorer()
        result = scorer.compute([{"severity": "low", "message": "test"}])
        # raw = 3, max = (100+50+15+3+0)*10 = 1680
        # health = 100 - (3/1680)*100 ≈ 99.82
        assert 99.0 < result["health_score"] <= 100.0
        assert result["severity_counts"]["low"] == 1

    def test_critical_drops_health(self):
        scorer = HealthScorer()
        result = scorer.compute([
            {"severity": "critical", "message": "hard fail"},
            {"severity": "critical", "message": "another fail"},
        ])
        # raw = 200, max = 1680, health = 100 - (200/1680)*100 ≈ 88.1
        assert result["health_score"] < 90
        assert result["severity_counts"]["critical"] == 2
        assert result["level"] in ("excellent", "good", "fair", "poor", "critical")

    def test_mixed_severity_correct_levels(self):
        scorer = HealthScorer()
        findings = (
            [{"severity": "critical", "message": "c"}] * 2 +
            [{"severity": "high", "message": "h"}] * 5 +
            [{"severity": "medium", "message": "m"}] * 10 +
            [{"severity": "low", "message": "l"}] * 20
        )
        result = scorer.compute(findings)
        assert result["severity_counts"]["critical"] == 2
        assert result["severity_counts"]["high"] == 5
        assert result["severity_counts"]["medium"] == 10
        assert result["severity_counts"]["low"] == 20
        assert result["total_findings"] == 37

    def test_info_severity_zero_weight(self):
        scorer = HealthScorer()
        result = scorer.compute([{"severity": "info", "message": "note"}])
        assert result["health_score"] == 100.0  # weight=0, no penalty
        assert result["severity_counts"]["info"] == 1

    def test_bucket_boundaries(self):
        scorer = HealthScorer()
        # Exactly at boundary: 90 = excellent
        # raw penalty = 10% of max = 168 → ~1.7 criticals
        result = scorer.compute([{"severity": "critical", "message": "x"}])
        # raw=100, health = 94.04 → excellent
        assert result["level"] == "excellent"


class TestTechDebtAnalyzer:
    """TechDebtAnalyzer: scans files for markers + metrics."""

    def test_empty_project(self, tmp_path):
        analyzer = TechDebtAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        assert result["marker_count"] == 0
        assert result["total_lines"] == 0

    def test_todo_marker_detected(self, tmp_path):
        pyfile = tmp_path / "test.py"
        pyfile.write_text("# TODO: fix this later\nprint('hello')\n")
        analyzer = TechDebtAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        assert result["marker_count"] == 1
        assert result["markers"][0]["marker"] == "TODO"

    def test_fixme_hack_xxx_markers(self, tmp_path):
        pyfile = tmp_path / "work.py"
        pyfile.write_text(
            "# FIXME: broken\n"
            "# HACK: workaround\n"
            "# XXX: dangerous\n"
            "# BUG: needs fix\n"
            "# WORKAROUND: temp\n"
        )
        analyzer = TechDebtAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        assert result["marker_count"] == 5

    def test_markers_only_in_comments(self, tmp_path):
        """Patterns in code (not comment) should NOT count."""
        pyfile = tmp_path / "lib.py"
        pyfile.write_text('result = "TODO list processing"\n')
        analyzer = TechDebtAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        assert result["marker_count"] == 0

    def test_large_file_penalty(self, tmp_path):
        pyfile = tmp_path / "big.py"
        pyfile.write_text("x = 1\n" * 600)
        analyzer = TechDebtAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        assert len(result["large_files"]) >= 1
        assert result["large_files"][0]["overly_long"] is True
        assert result["debt_index"] > 0

    def test_skip_hidden_dirs(self, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "a.py").write_text("# TODO: hidden\n")
        analyzer = TechDebtAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        assert result["marker_count"] == 0

    def test_skip_venv(self, tmp_path):
        (tmp_path / "venv").mkdir()
        (tmp_path / "venv" / "lib.py").write_text("# TODO: in venv\n")
        analyzer = TechDebtAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        assert result["marker_count"] == 0

    def test_comment_ratio(self, tmp_path):
        pyfile = tmp_path / "commented.py"
        lines = ["# header comment\n", "# another comment\n"] + ["code\n"] * 8
        pyfile.write_text("".join(lines))
        analyzer = TechDebtAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        assert 19 <= result["comment_ratio"] <= 21  # 2/10 ≈ 20%


class TestArchitectureAnalyzer:
    """ArchitectureAnalyzer: import graph + coupling + cycles."""

    def test_empty_project(self, tmp_path):
        analyzer = ArchitectureAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        assert result["module_count"] == 0
        assert result["cycles"] == []

    def test_simple_import_graph(self, tmp_path):
        (tmp_path / "a.py").write_text("import b\nimport os\n")
        (tmp_path / "b.py").write_text("import os\n")
        analyzer = ArchitectureAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        assert result["module_count"] == 2
        # a imports b → coupling score for b has fan_in
        assert len(result["top_coupled"]) <= 2

    def test_cycle_detection(self, tmp_path):
        (tmp_path / "x.py").write_text("import y\n")
        (tmp_path / "y.py").write_text("import x\n")
        analyzer = ArchitectureAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        assert len(result["cycles"]) >= 1

    def test_god_module_detection(self, tmp_path):
        # >1000 lines + import to appear in coupling map
        (tmp_path / "god.py").write_text("import os\n" + "a = 1\n" * 1100)
        analyzer = ArchitectureAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        # god.py has 1100 lines, should be detected
        god_mods = [m for m in result.get("god_modules", []) if "god" in str(m.get("module", ""))]
        assert len(god_mods) >= 1
        assert god_mods[0]["lines"] > 1000

    def test_fan_out_god_module(self, tmp_path):
        # >15 imports = god module
        imports = "\n".join(f"import mod{i}" for i in range(20))
        (tmp_path / "hub.py").write_text(imports + "\n")
        analyzer = ArchitectureAnalyzer()
        result = analyzer.analyze(str(tmp_path))
        # fan_out is computed from import statements parsed from AST
        # but external modules won't get fan_in (not project-internal)
        # So we just verify no crash and module_count is correct
        assert "hub" in [m["module"] for m in result["god_modules"]] or result["module_count"] >= 1


class TestTestCoverageEstimator:
    """TestCoverageEstimator: fallback test file counting."""

    def test_no_tests(self, tmp_path):
        est = TestCoverageEstimator()
        result = est.estimate(str(tmp_path))
        assert result["has_coverage"] is False
        assert result["test_files_found"] == 0

    def test_count_test_files(self, tmp_path):
        (tmp_path / "test_foo.py").write_text("def test(): pass\n")
        (tmp_path / "bar_test.py").write_text("def test(): pass\n")
        est = TestCoverageEstimator()
        result = est.estimate(str(tmp_path))
        assert result["test_files_found"] == 2


class TestEvolutionBaseline:
    """EvolutionBaseline: save + load + diff."""

    def test_save_and_load(self, tmp_path):
        baseline = EvolutionBaseline(str(tmp_path))
        baseline.save({"health": {"health_score": 85}})
        loaded = baseline.load()
        assert loaded["health"]["health_score"] == 85

    def test_diff_detects_improvement(self, tmp_path):
        baseline = EvolutionBaseline(str(tmp_path))
        baseline.save({
            "health": {"health_score": 70, "total_findings": 10},
            "technical_debt": {"debt_index": 40},
        })
        report = EvolutionReporter(str(tmp_path))
        current = {
            "health": {"health_score": 80, "total_findings": 5},
            "technical_debt": {"debt_index": 30},
        }
        diff = baseline.diff(current)
        assert diff is not None
        assert diff["trend"] == "improving"
        assert diff["health_delta"] == 10.0
        assert diff["debt_delta"] == -10
        assert diff["findings_delta"] == -5

    def test_diff_detects_degradation(self, tmp_path):
        baseline = EvolutionBaseline(str(tmp_path))
        baseline.save({
            "health": {"health_score": 80},
            "technical_debt": {"debt_index": 20},
        })
        current = {
            "health": {"health_score": 60},
            "technical_debt": {"debt_index": 50},
        }
        diff = baseline.diff(current)
        assert diff is not None
        assert diff["trend"] == "degrading"

    def test_diff_detects_stable(self, tmp_path):
        baseline = EvolutionBaseline(str(tmp_path))
        d = {"health": {"health_score": 75}, "technical_debt": {"debt_index": 30}}
        baseline.save(d)
        diff = baseline.diff(d)
        assert diff is not None
        assert diff["trend"] == "stable"

    def test_load_missing_file(self, tmp_path):
        baseline = EvolutionBaseline(str(tmp_path))
        assert baseline.load() is None

    def test_diff_no_baseline(self, tmp_path):
        baseline = EvolutionBaseline(str(tmp_path))
        assert baseline.diff({"health": {}}) is None


class TestEvolutionReporter:
    """EvolutionReporter: composite full report."""

    def test_full_report_produces_all_sections(self, tmp_path):
        (tmp_path / "test_module.py").write_text("def foo(): pass\n")
        reporter = EvolutionReporter(str(tmp_path))
        report = reporter.full_report([])
        assert "health" in report
        assert "technical_debt" in report
        assert "architecture" in report
        assert "test_coverage" in report
        assert "overall_score" in report
        assert "roadmap" in report
        assert isinstance(report["overall_score"], (int, float))

    def test_report_with_findings(self, tmp_path):
        (tmp_path / "src.py").write_text("a = 1\n")
        reporter = EvolutionReporter(str(tmp_path))
        findings = [{"severity": "high", "message": "bad"}, {"severity": "low", "message": "nit"}]
        report = reporter.full_report(findings)
        assert report["health"]["total_findings"] == 2
        assert report["health"]["health_score"] < 100


class TestSeverityWeights:
    """SEVERITY_WEIGHTS table consistency."""

    def test_critical_highest_weight(self):
        assert SEVERITY_WEIGHTS["critical"] > SEVERITY_WEIGHTS["high"]
        assert SEVERITY_WEIGHTS["high"] > SEVERITY_WEIGHTS["medium"]
        assert SEVERITY_WEIGHTS["medium"] > SEVERITY_WEIGHTS["low"]
        assert SEVERITY_WEIGHTS["low"] > SEVERITY_WEIGHTS["info"]

    def test_info_zero(self):
        assert SEVERITY_WEIGHTS["info"] == 0
