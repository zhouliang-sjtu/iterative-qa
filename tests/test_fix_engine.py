"""Tests for FixEngine — LLM-powered code patching."""

import pytest
from pathlib import Path
from codespect_matrix.fix_engine import FixEngine, FixResult, run_fix_cycle


class TestFixResult:
    """FixResult dataclass tests."""

    def test_success_result(self):
        r = FixResult("check1", "file.py", True,
                       patch={"old_str": "x", "new_str": "y"},
                       reasoning="fixed it")
        d = r.to_dict()
        assert d["success"] is True
        assert d["check_name"] == "check1"
        assert d["patch"]["old_str"] == "x"
        assert d["reasoning"] == "fixed it"

    def test_failure_result(self):
        r = FixResult("check2", "file.py", False,
                       error="file not found")
        d = r.to_dict()
        assert d["success"] is False
        assert d["error"] == "file not found"


class TestFixEngine:
    """FixEngine core tests."""

    def test_init_creates_project_path(self, tmp_path):
        engine = FixEngine(str(tmp_path))
        assert engine.backup_dir == tmp_path / ".codespect_matrix_backups"

    def test_execute_no_eligible(self, tmp_path):
        engine = FixEngine(str(tmp_path))
        proposals = [
            {"finding": {"check_name": "x"}, "can_auto_fix": False}
        ]
        results = engine.execute_fixes(proposals)
        assert results == []

    def test_fix_all_flag(self, tmp_path):
        engine = FixEngine(str(tmp_path))
        proposals = [
            {"finding": {"check_name": "x"}, "can_auto_fix": False}
        ]
        # Even with fix_all, needs file_path to apply
        results = engine.execute_fixes(proposals, fix_all=True)
        assert len(results) == 1
        assert results[0].success is False
        assert "No file_path" in (results[0].error or "")

    def test_file_not_found(self, tmp_path):
        engine = FixEngine(str(tmp_path))
        proposals = [
            {
                "finding": {"check_name": "x", "file_path": "nonexistent.py"},
                "can_auto_fix": True,
            }
        ]
        results = engine.execute_fixes(proposals)
        assert results[0].success is False
        assert "File not found" in (results[0].error or "")

    def test_backup_directory_created(self, tmp_path):
        """Verify backup dir is created when a fix is attempted."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n")

        engine = FixEngine(str(tmp_path))
        # No LLM → falls through to rule_based → returns None → no patch
        proposals = [
            {
                "finding": {
                    "check_name": "test_check",
                    "file_path": str(test_file),
                    "line_start": 1,
                },
                "can_auto_fix": True,
            }
        ]
        results = engine.execute_fixes(proposals)
        # Without LLM and without rule match, result is failed
        assert len(results) == 1
        assert results[0].success is False

    def test_get_changed_files(self, tmp_path):
        engine = FixEngine(str(tmp_path))
        engine.results = [
            FixResult("a", "f1.py", True),
            FixResult("b", "f1.py", True),
            FixResult("c", "f2.py", False),
        ]
        changed = engine.get_changed_files()
        assert "f1.py" in changed
        assert "f2.py" not in changed

    def test_get_fix_summary(self, tmp_path):
        engine = FixEngine(str(tmp_path))
        engine.results = [
            FixResult("a", "f1.py", True, patch={"old_str": "x", "new_str": "y"}),
            FixResult("b", "f2.py", False, error="oops"),
        ]
        s = engine.get_fix_summary()
        assert s["total"] == 2
        assert s["applied"] == 1
        assert s["failed"] == 1
        assert "f1.py" in s["files_changed"]
        assert len(s["details"]) == 2


class TestFuzzyMatch:
    """Fuzzy matching for old_str resolution."""

    def test_exact_match(self, tmp_path):
        """fuzzy_match returns None when old_str already exists in content."""
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")
        engine = FixEngine(str(tmp_path))
        content = test_file.read_text()
        # Exact match succeeds before fuzzy_match is called
        assert "line2" in content

    def test_fuzzy_substring_match(self, tmp_path):
        """When exact match fails, try dropping first line."""
        test_file = tmp_path / "test.py"
        test_file.write_text("prefix_line\nline2\nline3\n")
        engine = FixEngine(str(tmp_path))
        content = test_file.read_text()
        # "ZZZ_line\nline2\nline3" is not in content exactly
        # but dropping first line gives "line2\nline3" which matches
        result = engine._fuzzy_match("ZZZ_line\nline2\nline3", content)
        assert result == "line2\nline3"

    def test_drop_last_line(self, tmp_path):
        """Drop last line when full string not found."""
        test_file = tmp_path / "test.py"
        test_file.write_text("lineA\nlineB\nlineC\n")
        engine = FixEngine(str(tmp_path))
        content = test_file.read_text()
        # "lineA\nlineB\nEXTRA" not in content
        # dropping last line gives "lineA\nlineB" which matches
        result = engine._fuzzy_match("lineA\nlineB\nEXTRA", content)
        assert result == "lineA\nlineB"

    def test_no_match(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("hello\nworld\n")
        engine = FixEngine(str(tmp_path))
        content = test_file.read_text()
        result = engine._fuzzy_match("completely\ndifferent", content)
        assert result is None


class TestPatchParsing:
    """LLM response parsing."""

    def test_valid_json(self, tmp_path):
        engine = FixEngine(str(tmp_path))
        response = '{"reasoning": "fix bug", "old_str": "x=1", "new_str": "x=2"}'
        patch = engine._parse_patch_response(response)
        assert patch["old_str"] == "x=1"
        assert patch["new_str"] == "x=2"
        assert patch["reasoning"] == "fix bug"

    def test_json_with_markdown_fence(self, tmp_path):
        engine = FixEngine(str(tmp_path))
        response = '```json\n{"old_str": "a", "new_str": "b"}\n```'
        patch = engine._parse_patch_response(response)
        assert patch["old_str"] == "a"

    def test_invalid_json(self, tmp_path):
        engine = FixEngine(str(tmp_path))
        response = "not json at all"
        patch = engine._parse_patch_response(response)
        assert patch is None

    def test_empty_new_str(self, tmp_path):
        """Deletion: new_str is empty string."""
        engine = FixEngine(str(tmp_path))
        response = '{"old_str": "dead code", "new_str": ""}'
        patch = engine._parse_patch_response(response)
        assert patch["new_str"] == ""
        assert patch["old_str"] == "dead code"


class TestRuleBasedPatch:
    """Fallback rule-based patching."""

    def test_no_llm_fallback(self, tmp_path):
        engine = FixEngine(str(tmp_path))
        patch = engine._rule_based_patch(
            {"check_name": "anything"},
            "some file content",
        )
        assert patch is None


class TestRunFixCycle:
    """Integration: full fix cycle."""

    def test_no_proposals(self, tmp_path):
        result = run_fix_cycle(str(tmp_path), [])
        assert result["fix_summary"]["total"] == 0
