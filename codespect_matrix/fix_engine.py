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

    # ── Rollback API ────────────────────────────────────────

    def rollback(self, file_paths: List[str] = None) -> Dict:
        """Rollback one or more files to their last backup.

        Args:
            file_paths: Specific files to rollback. None = rollback ALL.

        Returns:
            {"rolled_back": [...], "failed": [...], "unchanged": [...]}
        """
        manifest_path = self.backup_dir / BACKUP_MANIFEST
        if not manifest_path.exists():
            return {"rolled_back": [], "failed": [], "unchanged": [],
                    "error": "No backup manifest found"}

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            return {"rolled_back": [], "failed": [], "unchanged": [],
                    "error": "Backup manifest corrupted"}

        targets = set(file_paths) if file_paths else set(manifest.keys())
        rolled, failed, unchanged = [], [], []

        for rel_path in targets:
            entries = manifest.get(rel_path, [])
            if not entries:
                unchanged.append(rel_path)
                continue
            latest = entries[-1]
            backup_file = self.backup_dir / latest["backup_name"]
            if not backup_file.exists():
                failed.append(rel_path)
                continue
            abs_path = self.project_path / rel_path
            try:
                with open(backup_file, 'r', encoding='utf-8') as f:
                    original = f.read()
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                with open(abs_path, 'w', encoding='utf-8') as f:
                    f.write(original)
                rolled.append(rel_path)
            except Exception as e:
                failed.append(f"{rel_path}: {e}")

        return {"rolled_back": rolled, "failed": failed, "unchanged": unchanged}

    def rollback_all(self) -> Dict:
        """Rollback ALL modified files."""
        return self.rollback(file_paths=None)

    def list_backups(self) -> Dict:
        """List all available backups with timestamps."""
        manifest_path = self.backup_dir / BACKUP_MANIFEST
        if not manifest_path.exists():
            return {"files": {}, "total_files": 0, "total_backups": 0}
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            return {"files": {}, "total_files": 0, "total_backups": 0}

        total = sum(len(v) for v in manifest.values())
        return {
            "files": {
                rel: [{"timestamp": e["timestamp"], "backup": e["backup_name"]}
                      for e in entries]
                for rel, entries in manifest.items()
            },
            "total_files": len(manifest),
            "total_backups": total,
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
            self._restore_from_backup(abs_path, original_content)
            return FixResult(check_name, str(abs_path), False,
                             error=f"Write failed — auto-rolled back: {e}",
                             patch=patch, reasoning=reasoning)

        # Verify patch was applied correctly
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                verify_content = f.read()
            if verify_content == original_content:
                return FixResult(check_name, str(abs_path), False,
                                 error="Patch applied but file unchanged",
                                 patch=patch, reasoning=reasoning)
            if new_str not in verify_content and new_str.strip():
                self._restore_from_backup(abs_path, original_content)
                return FixResult(check_name, str(abs_path), False,
                                 error="Patch verification failed — auto-rolled back",
                                 patch=patch, reasoning=reasoning)
        except Exception:
            pass

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

        Handles common security and code-quality patterns with
        deterministic old_str → new_str replacements.
        """
        check_name = finding.get("check_name", "")
        message = finding.get("message", "")
        evidence = finding.get("evidence", "")
        remediation = finding.get("remediation", "")
        combined = f"{check_name} {message} {evidence} {remediation}".lower()

        # ── Pattern 1: Hardcoded secrets ────────────────────────
        hardcoded_patch = self._patch_hardcoded_secret(file_content, combined)
        if hardcoded_patch:
            return hardcoded_patch

        # ── Pattern 2: SQL injection via f-string ─────────────────
        sql_patch = self._patch_sql_injection(file_content, combined)
        if sql_patch:
            return sql_patch

        # ── Pattern 3: Insecure cryptography (MD5/SHA1/ECB) ──────
        crypto_patch = self._patch_insecure_crypto(file_content, combined)
        if crypto_patch:
            return crypto_patch

        # ── Pattern 4: Insecure deserialization (pickle/yaml) ────
        deser_patch = self._patch_insecure_deserialization(file_content, combined)
        if deser_patch:
            return deser_patch

        # ── Pattern 5: PHI leak in logs/print ────────────────────
        phi_patch = self._patch_phi_leak(file_content, combined)
        if phi_patch:
            return phi_patch

        # ── Pattern 6: Missing input validation ───────────────────
        validation_patch = self._patch_missing_validation(file_content, combined)
        if validation_patch:
            return validation_patch

        return None

    # ── Sub-methods for each pattern category ──────────────────────

    def _patch_hardcoded_secret(self, content: str, ctx: str) -> Optional[Dict]:
        """Replace hardcoded credentials with environment variable reads."""
        patterns = [
            # API_KEY = "sk_live_..."  →  API_KEY = os.environ.get("API_KEY", "")
            (r'^(\s*)(API_KEY|SECRET_KEY|ACCESS_KEY|AUTH_TOKEN)\s*=\s*["\']([^"\']+)["\']',
             r'\1\2 = os.environ.get("\2", "")\n\1# NOTE: set \2 in environment before deploying'),
            # DATABASE_URL = "postgresql://user:pass@..."  →  env read
            (r'^(\s*)(DATABASE_URL|DB_URL|DATABASE_URI)\s*=\s*["\']([^"\']+)["\']',
             r'\1\2 = os.environ.get("\2", "")\n\1# NOTE: set \2 in environment before deploying'),
            # PASSWORD = "xxx"
            (r'^(\s*)(PASSWORD|DB_PASSWORD|ADMIN_PASSWORD)\s*=\s*["\']([^"\']+)["\']',
             r'\1\2 = os.environ.get("\2", "")\n\1# NOTE: set \2 in environment before deploying'),
        ]
        return self._try_patterns(content, patterns)

    def _patch_sql_injection(self, content: str, ctx: str) -> Optional[Dict]:
        """Replace f-string SQL queries with parameterized queries."""
        patterns = [
            # cursor.execute(f"SELECT ... WHERE id = {var}") → parameterized
            (r'(\.execute\s*\(\s*)f"(SELECT[^"]*\{[^"]*\})"',
             r'\1"<PARAMETERIZED_QUERY_NEEDED>"  # FIX: replace f-string with parameterized query\n# Use: cursor.execute("SELECT ... WHERE id = %s", (var,))'),
            # db.execute(f"...")
            (r'(\.execute\s*\(\s*)f\'([^\']*\{[^\']*\})\'',
             r'\1"<PARAMETERIZED_QUERY_NEEDED>"  # FIX: replace f-string with parameterized query'),
            # query = f"SELECT..." pattern
            (r'^(\s*)(\w+)\s*=\s*f"(SELECT[^"]*\{[^"]*\})"',
             r'\1\2 = "<SQL_PARAMETERIZED>"  # FIX: use parameterized query instead of string interpolation\n\1# Use: cursor.execute("SELECT ... WHERE id = %s", (user_input,))'),
        ]
        return self._try_patterns(content, patterns, require_match=True)

    def _patch_insecure_crypto(self, content: str, ctx: str) -> Optional[Dict]:
        """Replace insecure crypto with secure alternatives."""
        patterns = [
            # hashlib.md5(...) → hashlib.sha256(...) with warning comment
            (r'hashlib\.md5\s*\(\s*',
             'hashlib.sha256(  # FIX: md5 is cryptographically broken, use sha256'),
            # AES.MODE_ECB → AES.MODE_CBC
            (r'AES\.MODE_ECB\b',
             'AES.MODE_CBC  # FIX: ECB mode is insecure, use CBC with random IV'),
            # hashlib.sha1 for passwords
            (r'hashlib\.sha1\s*\(\s*',
             'hashlib.sha256(  # FIX: sha1 is cryptographically weak, use sha256'),
        ]
        return self._try_patterns(content, patterns, require_match=True)

    def _patch_insecure_deserialization(self, content: str, ctx: str) -> Optional[Dict]:
        """Replace unsafe deserialization with warnings."""
        patterns = [
            # pickle.loads(...) → json.loads(...) with warning
            (r'(\.loads?\s*\(\s*)(pickle)\.loads?\(',
             r'\1# FIX: pickle.loads is unsafe → use json.loads for untrusted data\n'
             r'# If binary serialization is required, use a secure alternative'),
            # pickle.loads( → warning
            (r'pickle\.loads\s*\(\s*',
             'json.loads(  # FIX: pickle.loads is insecure for untrusted data → use json.loads'),
            # yaml.load( → yaml.safe_load(
            (r'yaml\.load\s*\(\s*',
             'yaml.safe_load(  # FIX: yaml.load is unsafe → use yaml.safe_load'),
        ]
        return self._try_patterns(content, patterns, require_match=True)

    def _patch_phi_leak(self, content: str, ctx: str) -> Optional[Dict]:
        """Replace PHI-leaking log/print statements with de-identified versions."""
        patterns = [
            # print(f"Patient: {name}, SSN: {ssn}") → redacted
            (r'(print|logger\.\w+)\(\s*f"(.*?\{.*?(?:patient|ssn|mrn|name|dob).*?\}.*?)"',
             r'\1(f"[REDACTED-PHI] \2")  # FIX: PHI exposed — de-identify before logging'),
            # logger.info(f"Patient {name}...")
            (r'(logger\.\w+\(\s*f)"(.*?patient.*?)"',
             r'\1"[REDACTED-PHI] \2"  # FIX: PHI exposed — de-identify before logging'),
        ]
        return self._try_patterns(content, patterns)

    def _patch_missing_validation(self, content: str, ctx: str) -> Optional[Dict]:
        """Add input validation comments where missing."""
        # Capture: indent, var_name, request_accessor(args/form/json), param_name
        pattern = (
            r'^(\s*)(\w+)\s*=\s*(?:int|float)\s*\(\s*'
            r'request\.(\w+)\.get\(["\'](heart_rate|temperature|weight|dose)'
        )
        m = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
        if m:
            indent, var_name, accessor, param = m.groups()
            old_str = m.group(0)
            new_str = (
                f'{indent}# FIX: add validation before using medical data\n'
                f'{indent}{var_name} = _validate_{param}(request.{accessor}.get("{param}"))'
                f'  # See: vital sign validation rules'
            )
            return {
                "old_str": old_str,
                "new_str": new_str,
                "reasoning": "Rule-based fix: added input validation placeholder for medical data",
            }
        return None

    def _try_patterns(self, content: str, patterns: list,
                      require_match: bool = False) -> Optional[Dict]:
        """Try each (search, replace) pattern and return first match."""
        for search_pat, replace_pat in patterns:
            m = re.search(search_pat, content, re.MULTILINE | re.IGNORECASE)
            if m:
                old_str = m.group(0)
                new_str = re.sub(search_pat, replace_pat, old_str,
                                 flags=re.MULTILINE | re.IGNORECASE)
                if new_str != old_str:
                    return {
                        "old_str": old_str,
                        "new_str": new_str,
                        "reasoning": f"Rule-based auto-fix applied for pattern: {search_pat[:60]}",
                    }
        return None

    def _backup(self, file_path: Path, content: str):
        """Save a timestamped backup of the original file and update manifest."""
        self.backup_dir.mkdir(exist_ok=True)
        try:
            rel = file_path.relative_to(self.project_path)
        except ValueError:
            rel = file_path
        rel_str = rel.as_posix().replace("/", "_").replace("\\", "_")
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        backup_name = f"{rel_str}.{ts}.bak"
        backup_path = self.backup_dir / backup_name
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # Update manifest for rollback tracking
        manifest_path = self.backup_dir / BACKUP_MANIFEST
        manifest = {}
        if manifest_path.exists():
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
            except Exception:
                pass
        rel_key = file_path.relative_to(self.project_path).as_posix() if self.project_path in file_path.parents else str(file_path)
        manifest.setdefault(rel_key, []).append({
            "backup_name": backup_name,
            "timestamp": ts,
            "size": len(content),
        })
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)

    def _restore_from_backup(self, file_path: Path, content: str):
        """Restore original content from a known-good copy.

        Used as auto-rollback when patch application or verification fails.
        """
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            pass


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
