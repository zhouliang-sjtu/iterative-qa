"""FixEngine — LLM-powered code patching with backup and SelfEvolver integration.

Workflow:
1. Take fix proposals → build LLM prompt with file context
2. LLM generates precise old_str/new_str patches
3. Backup originals to .codespect_matrix_backups/
4. Apply patches via SearchReplace
5. Re-scan to verify health improvement
6. Record in SelfEvolver for learning
"""

from __future__ import annotations

import os
import re
import json
import shutil
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


# ═══════════════════════════════════════════════════════════
# Fix result dataclass
# ═══════════════════════════════════════════════════════════


class FixResult:
    """Outcome of a single fix attempt."""

    def __init__(self, check_name: str, file_path: str, success: bool,
                 patch: Dict = None, error: str = None,
                 reasoning: str = ""):
        self.check_name = check_name
        self.file_path = file_path
        self.success = success
        self.patch = patch or {}
        self.error = error
        self.reasoning = reasoning

    def to_dict(self) -> Dict:
        return {
            "check_name": self.check_name,
            "file_path": self.file_path,
            "success": self.success,
            "patch": self.patch,
            "error": self.error,
            "reasoning": self.reasoning,
        }


# ═══════════════════════════════════════════════════════════
# FixEngine
# ═══════════════════════════════════════════════════════════

BACKUP_DIR_NAME = ".codespect_matrix_backups"
PATCH_JSON_KEY = "patches"


class FixEngine:
    """LLM-driven code patching engine.

    Generates precise old_str/new_str diffs via LLM, applies them to
    source files with automatic backup, and feeds results into the
    SelfEvolver for continuous learning.
    """

    def __init__(self, project_path: str, llm_service=None):
        self.project_path = Path(project_path).resolve()
        self.backup_dir = self.project_path / BACKUP_DIR_NAME
        self.llm = llm_service
        self.results: List[FixResult] = []

    # ── Public API ──────────────────────────────────────────

    def execute_fixes(self, proposals: List[Dict],
                      fix_all: bool = False) -> List[FixResult]:
        """Execute all eligible fix proposals.

        Args:
            proposals: list from orchestrator.generate_fix_proposals()
            fix_all: if True, attempt even low-confidence fixes

        Returns:
            list of FixResult with success/failure per fix
        """
        eligible = [
            p for p in proposals
            if fix_all or p.get("can_auto_fix", False)
        ]
        if not eligible:
            return []

        self.results = []
        for proposal in eligible:
            result = self._apply_one(proposal)
            self.results.append(result)

        return self.results

    def get_changed_files(self) -> List[str]:
        """Return list of file paths that were modified."""
        return list(set(
            r.file_path for r in self.results if r.success
        ))

    def get_fix_summary(self) -> Dict:
        """Human-readable fix summary."""
        success = [r for r in self.results if r.success]
        failed = [r for r in self.results if not r.success]
        return {
            "total": len(self.results),
            "applied": len(success),
            "failed": len(failed),
            "files_changed": self.get_changed_files(),
            "details": [r.to_dict() for r in self.results],
        }

    # ── Internal ────────────────────────────────────────────

    def _apply_one(self, proposal: Dict) -> FixResult:
        """Apply a single fix proposal."""
        finding = proposal.get("finding", {})
        check_name = finding.get("check_name", "unknown")
        file_path = finding.get("file_path", "")

        # Resolve absolute path
        if file_path:
            if not os.path.isabs(file_path):
                abs_path = self.project_path / file_path
            else:
                abs_path = Path(file_path)
        else:
            return FixResult(check_name, "", False,
                             error="No file_path in finding — cannot apply fix")

        abs_path = abs_path.resolve()
        if not abs_path.exists():
            return FixResult(check_name, str(abs_path), False,
                             error=f"File not found: {abs_path}")

        # Read file content
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
        except Exception as e:
            return FixResult(check_name, str(abs_path), False,
                             error=f"Cannot read file: {e}")

        # Generate patch via LLM
        patch = self._generate_patch(finding, original_content, str(abs_path))
        if not patch:
            return FixResult(check_name, str(abs_path), False,
                             error="LLM could not generate a patch")

        old_str = patch.get("old_str", "")
        new_str = patch.get("new_str", "")
        reasoning = patch.get("reasoning", "")

        if not old_str:
            return FixResult(check_name, str(abs_path), False,
                             error="Patch has no old_str", reasoning=reasoning)

        # Verify old_str exists in file
        if old_str not in original_content:
            # Try fuzzy match with surrounding context
            old_str = self._fuzzy_match(old_str, original_content)
            if not old_str:
                return FixResult(check_name, str(abs_path), False,
                                 error="old_str not found in file (fuzzy match also failed)",
                                 reasoning=reasoning)

        # Backup before modifying
        self._backup(abs_path, original_content)

        # Apply patch
        new_content = original_content.replace(old_str, new_str, 1)
        try:
            with open(abs_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
        except Exception as e:
            return FixResult(check_name, str(abs_path), False,
                             error=f"Cannot write file: {e}",
                             patch=patch, reasoning=reasoning)

        return FixResult(check_name, str(abs_path), True,
                         patch=patch, reasoning=reasoning)

    def _generate_patch(self, finding: Dict, file_content: str,
                        file_path: str) -> Optional[Dict]:
        """Ask LLM to generate a precise old_str/new_str patch.

        Truncates long files to relevant context around the reported line.
        """
        if not self.llm:
            return self._rule_based_patch(finding, file_content)

        line_start = finding.get("line_start", 0)
        check_name = finding.get("check_name", "")
        message = finding.get("message", "")
        remediation = finding.get("remediation", "")
        severity = finding.get("severity", "medium")
        lines = file_content.splitlines()

        # Extract context around the reported line
        ctx_start = max(0, line_start - 15)
        ctx_end = min(len(lines), line_start + 15)
        context_lines = lines[ctx_start:ctx_end]
        context = "\n".join(
            f"{ctx_start + i + 1}: {line}"
            for i, line in enumerate(context_lines)
        )

        prompt = self._build_patch_prompt(
            check_name=check_name,
            severity=severity,
            message=message,
            remediation=remediation,
            file_path=file_path,
            context=context,
            context_start=ctx_start + 1,
        )

        try:
            response = self.llm.generate(prompt, temperature=0.1, max_tokens=2048)
            return self._parse_patch_response(response)
        except Exception as e:
            return None

    def _build_patch_prompt(self, check_name: str, severity: str,
                            message: str, remediation: str,
                            file_path: str, context: str,
                            context_start: int) -> str:
        """Build the LLM prompt for patch generation."""
        return f"""You are a code fix engine. Generate an exact code patch.

ISSUE:
- check: {check_name}
- severity: {severity}
- message: {message}
- suggested fix: {remediation}

FILE: {file_path}

CODE CONTEXT (lines {context_start}+):
```
{context}
```

OUTPUT FORMAT — respond with ONLY this JSON (no markdown, no explanation):
{{
  "reasoning": "<1-2 sentence explanation of the fix>",
  "old_str": "<EXACT code to replace — MUST match the file character-by-character>",
  "new_str": "<replacement code>"
}}

RULES:
1. old_str MUST exist exactly in the file — copy-paste from the context above
2. new_str should be the minimal fix — change only what's needed
3. Do NOT add extra imports, comments, or formatting changes unless necessary
4. If the fix involves deleting code, set new_str to ""
5. Keep indentation exactly as in the original
6. Respond with ONLY the JSON object, no other text"""

    def _parse_patch_response(self, response: str) -> Optional[Dict]:
        """Parse LLM response into a patch dict."""
        # Strip code fences if present
        cleaned = response.strip()
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            patch = json.loads(cleaned)
            if "old_str" in patch and "new_str" in patch:
                return patch
        except json.JSONDecodeError:
            # Try to extract JSON from the response
            match = re.search(r'\{[^{}]*"old_str"[^{}]*\}', cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None

    def _fuzzy_match(self, old_str: str, content: str) -> Optional[str]:
        """Try to find a matching substring when exact match fails.

        Strategies:
        1. Try matching a substring of old_str (drop first/last line)
        2. Try matching with normalized whitespace
        """
        lines = old_str.splitlines()

        # Strategy 1: drop first line
        if len(lines) > 1:
            candidate = "\n".join(lines[1:])
            if candidate and candidate in content:
                return candidate

        # Strategy 2: drop last line
        if len(lines) > 1:
            candidate = "\n".join(lines[:-1])
            if candidate and candidate in content:
                return candidate

        # Strategy 3: drop both first and last lines
        if len(lines) > 2:
            candidate = "\n".join(lines[1:-1])
            if candidate and candidate in content:
                return candidate

        # Strategy 4: try each line individually, use longest match
        for line in sorted(lines, key=len, reverse=True):
            if len(line) > 10 and line in content:
                return line

        return None

    def _rule_based_patch(self, finding: Dict, file_content: str) -> Optional[Dict]:
        """Fallback rule-based patching when no LLM is available.

        Handles simple, well-known patterns.
        """
        check_name = finding.get("check_name", "")
        lines = file_content.splitlines()

        # Pattern: missing `__init__.py` or empty module docstrings are
        # structural issues that require manual intervention
        return None

    def _backup(self, file_path: Path, content: str):
        """Save a timestamped backup of the original file."""
        self.backup_dir.mkdir(exist_ok=True)
        rel = file_path.relative_to(self.project_path)
        backup_name = rel.as_posix().replace("/", "_").replace("\\", "_")
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"{backup_name}.{ts}.bak"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)


# ═══════════════════════════════════════════════════════════
# Convenience: run full fix-and-verify cycle
# ═══════════════════════════════════════════════════════════

def run_fix_cycle(project_path: str, proposals: List[Dict],
                  fix_all: bool = False,
                  orchestrator=None,
                  llm_service=None) -> Dict:
    """Run the complete fix cycle: apply → verify → learn.

    Args:
        project_path: project root
        proposals: fix proposals from orchestrator
        fix_all: attempt all fixes including low-confidence
        orchestrator: AgentOrchestrator instance for re-scan
        llm_service: LLM service for patch generation

    Returns:
        full cycle summary dict
    """
    from codespect_matrix.evolution import SelfEvolver

    # Step 1: Execute fixes
    engine = FixEngine(project_path, llm_service)
    results = engine.execute_fixes(proposals, fix_all=fix_all)
    fix_summary = engine.get_fix_summary()

    # Step 2: Re-scan to verify
    after_health = None
    health_delta = None
    if orchestrator and fix_summary["applied"] > 0:
        try:
            from codespect_matrix.evolution import HealthScorer
            # Run a fresh scan
            orchestrator.all_findings = []
            orchestrator.inspect_phase()
            orchestrator.review_phase()
            confirmed = [f for f in orchestrator.all_findings
                         if f.ruling == "confirmed"]
            scorer = HealthScorer()
            after = scorer.compute(
                [f.to_dict() for f in confirmed],
            )
            after_health = round(after.get("health_score", 0), 1)
        except Exception:
            pass

    # Step 3: Record in SelfEvolver
    try:
        evolver = SelfEvolver()
        findings_data = [
            r.to_dict() for r in results
        ]
        fixes_data = [
            {
                "check_name": r.check_name,
                "success": r.success,
            }
            for r in results
        ]
        fix_details = [
            {
                "check_name": r.check_name,
                "reasoning": r.reasoning,
                "old_code": r.patch.get("old_str", "")[:200],
                "new_code": r.patch.get("new_str", "")[:200],
            }
            for r in results if r.success and r.reasoning
        ]

        if fix_details:
            evolver.record_qa_cycle(
                project_name=Path(project_path).name,
                before_health=0,  # Will be set by caller
                findings=findings_data,
                fixes_applied=fixes_data,
                after_health=after_health,
                fix_details=fix_details,
            )
    except Exception:
        pass

    return {
        "fix_summary": fix_summary,
        "after_health": after_health,
        "health_delta": health_delta,
        "backup_dir": str(engine.backup_dir),
    }
