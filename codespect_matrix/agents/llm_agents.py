"""LLM-driven agents — pure reasoning domain specialists.

Each agent has an independent system prompt and review perspective.
Selected at runtime by Orchestrator based on project profile.
"""

from __future__ import annotations

import os
import json
import subprocess
from typing import Dict, List, Any

from .base import BaseAgent, AgentRole, Finding


# ─────────────────────────────────────────────
# LLM agent inspect factory
# ─────────────────────────────────────────────

def _llm_inspect(agent_name: str, system_prompt: str, domain: str,
                 files_context: str, project_profile: Dict, llm) -> List[Finding]:
    """Generic LLM-based inspection function."""
    if not llm or not files_context:
        return []

    profile_text = f"""
Project type: {project_profile.get('project_type', 'unknown')}
Tech stack: {', '.join(project_profile.get('tech_stack', []))}
Scale: {project_profile.get('scale', 'unknown')}
Domain: {project_profile.get('domain', 'unknown')}
"""

    prompt = f"""{system_prompt}

## Project Profile
{profile_text}

## Source Code
{files_context[:12000]}

## Task
As a {domain} expert, review the code above. Output one JSON object per finding (one per line):
{{"check_name":"{agent_name}_xxx", "severity":"critical|high|medium|low|info", "message":"issue description", "file_path":"relative path", "line_start":line, "evidence":"relevant code (max 200 chars)", "remediation":"fix suggestion"}}

Notes:
- Only report real issues, do not speculate
- If code looks fine, return empty array []
- severity: critical (security/data leak) > high (serious bug) > medium (code smell) > low (style) > info (suggestion)
- Return ONLY the JSON array, no other text

JSON:"""

    try:
        result = llm.generate(prompt, temperature=0.3, max_tokens=4096)
        start = result.find("[")
        end = result.rfind("]") + 1
        if start != -1 and end != 0:
            items = json.loads(result[start:end])
            findings = []
            for item in items:
                f = Finding(
                    check_name=item.get("check_name", f"{agent_name}_check"),
                    severity=item.get("severity", "low"),
                    message=item.get("message", ""),
                    file_path=item.get("file_path", ""),
                    line_start=item.get("line_start", 0),
                    evidence=item.get("evidence", ""),
                    remediation=item.get("remediation", ""),
                    confidence=0.75,
                )
                findings.append(f)
            return findings
    except Exception:
        pass
    return []


# ─────────────────────────────────────────────
# Code Quality Agent
# ─────────────────────────────────────────────

class DeveloperAgent(BaseAgent):
    """Code quality and correctness agent."""

    def get_description(self) -> str:
        return "Code quality, type safety, error handling, naming conventions"
    def get_domain(self) -> str:
        return "code_quality"

    def inspect(self, files_context: str) -> List[Finding]:
        return _llm_inspect("developer", """You are a senior code reviewer. Inspect:
1. Type safety and error handling
2. Function complexity and readability
3. Naming conventions and code organization
4. Potential null/undefined behavior
5. Unreasonable dependencies""", "code quality", files_context, self.project_profile, self.llm)


# ─────────────────────────────────────────────
# Architecture Agent
# ─────────────────────────────────────────────

class ArchitectAgent(BaseAgent):
    """Architecture and design review agent."""

    def get_description(self) -> str:
        return "System architecture, module coupling, technical debt"
    def get_domain(self) -> str:
        return "architecture"

    def inspect(self, files_context: str) -> List[Finding]:
        return _llm_inspect("architect", """You are a system architect. Inspect:
1. Inter-module coupling
2. Circular dependencies
3. Single Responsibility Principle violations
4. Interface design issues
5. Extensibility and maintainability""", "architecture", files_context, self.project_profile, self.llm)


# ─────────────────────────────────────────────
# Performance Agent
# ─────────────────────────────────────────────

class PerformanceAgent(BaseAgent):
    """Performance optimization agent."""

    def get_description(self) -> str:
        return "Performance bottlenecks, resource consumption, response time"
    def get_domain(self) -> str:
        return "performance"

    def inspect(self, files_context: str) -> List[Finding]:
        return _llm_inspect("performance", """You are a performance expert. Inspect:
1. Unnecessary nested loops
2. Inefficient data structure choices
3. N+1 query patterns
4. Missing cache mechanisms
5. Blocking I/O operations""", "performance", files_context, self.project_profile, self.llm)


# ─────────────────────────────────────────────
# DevOps Agent
# ─────────────────────────────────────────────

class DevOpsAgent(BaseAgent):
    """DevOps and observability agent."""

    def get_description(self) -> str:
        return "Observability, fault tolerance, scalability"
    def get_domain(self) -> str:
        return "devops"

    def inspect(self, files_context: str) -> List[Finding]:
        return _llm_inspect("devops", """You are a DevOps expert. Inspect:
1. Missing logging/monitoring instrumentation
2. Hardcoded config instead of environment variables
3. Missing health check endpoints
4. No graceful shutdown mechanism
5. Missing CI/CD configuration""", "DevOps", files_context, self.project_profile, self.llm)


# ─────────────────────────────────────────────
# Testing Agent
# ─────────────────────────────────────────────

class TestAgent(BaseAgent):
    """Testing strategy agent."""

    def get_description(self) -> str:
        return "Test coverage, test quality, testability"
    def get_domain(self) -> str:
        return "testing"

    def inspect(self, files_context: str) -> List[Finding]:
        return _llm_inspect("testing", """You are a testing expert. Inspect:
1. Missing unit tests for critical functions
2. Low test coverage modules
3. Test code quality issues
4. Missing integration/E2E tests
5. Untestable code patterns""", "testing", files_context, self.project_profile, self.llm)


# ─────────────────────────────────────────────
# API Design Agent
# ─────────────────────────────────────────────

class APIAgent(BaseAgent):
    """API design and contract agent."""

    def get_description(self) -> str:
        return "API design, interface contracts, versioning"
    def get_domain(self) -> str:
        return "api_design"

    def inspect(self, files_context: str) -> List[Finding]:
        return _llm_inspect("api", """You are an API design expert. Inspect:
1. RESTful convention violations
2. Missing input validation
3. Inconsistent error response format
4. Missing rate limiting
5. Missing authentication/authorization""", "API design", files_context, self.project_profile, self.llm)


# ─────────────────────────────────────────────
# Dependency Agent
# ─────────────────────────────────────────────

class DependencyAgent(BaseAgent):
    """Dependency management agent."""

    def get_description(self) -> str:
        return "Dependency versions, known CVEs, license compliance"
    def get_domain(self) -> str:
        return "dependencies"

    def inspect(self, files_context: str) -> List[Finding]:
        return _llm_inspect("dependency", """You are a dependency management expert. Inspect:
1. Outdated dependency versions
2. Dependencies with known CVEs
3. License conflicts
4. Unnecessary heavyweight dependencies
5. Unpinned direct dependency versions""", "dependency management", files_context, self.project_profile, self.llm)


# ─────────────────────────────────────────────
# Concurrency Agent
# ─────────────────────────────────────────────

class ConcurrencyAgent(BaseAgent):
    """Concurrency safety agent."""

    def get_description(self) -> str:
        return "Race conditions, deadlocks, thread safety"
    def get_domain(self) -> str:
        return "concurrency"

    def inspect(self, files_context: str) -> List[Finding]:
        return _llm_inspect("concurrency", """You are a concurrency safety expert. Inspect:
1. Potential race conditions
2. Unlocked shared mutable state
3. Deadlock risks
4. Thread-unsafe Singletons/caches
5. Blocking calls in async code""", "concurrency", files_context, self.project_profile, self.llm)


# ─────────────────────────────────────────────
# NEW: Linter Agent — wraps ruff/flake8/mypy
# ─────────────────────────────────────────────

class LinterAgent(BaseAgent):
    """Static analysis agent — runs linters and interprets results via LLM."""

    def get_description(self) -> str:
        return "Static analysis: ruff, flake8, mypy, pylint — LLM-interpreted"
    def get_domain(self) -> str:
        return "linting"

    def _run_ruff(self, project_path: str) -> str:
        try:
            result = subprocess.run(
                ["ruff", "check", project_path, "--output-format", "text"],
                capture_output=True, text=True, timeout=60,
            )
            return result.stdout.strip() or "No ruff issues found."
        except Exception:
            return ""

    def _run_mypy(self, project_path: str) -> str:
        try:
            result = subprocess.run(
                ["mypy", project_path, "--ignore-missing-imports"],
                capture_output=True, text=True, timeout=120,
            )
            return result.stdout.strip() or "No mypy issues found."
        except Exception:
            return ""

    def inspect(self, files_context: str) -> List[Finding]:
        findings = []

        # 1. Ruff scan
        ruff_output = self._run_ruff(self.project_path)
        if ruff_output and self.llm:
            prompt = f"""[RUFF OUTPUT]
{ruff_output[:4000]}

Interpret the ruff output. For each finding output:
{{"check_name":"linter_ruff_xxx", "severity":"...", "message":"..."}}
Return JSON array only."""
            try:
                result = self.llm.generate(prompt, temperature=0.2, max_tokens=2000)
                start, end = result.find("["), result.rfind("]") + 1
                if start != -1 and end != 0:
                    for item in json.loads(result[start:end]):
                        findings.append(Finding(**item, confidence=0.9))
            except Exception:
                pass

        # 2. Mypy scan
        mypy_output = self._run_mypy(self.project_path)
        if mypy_output and self.llm:
            prompt = f"""[MYPY OUTPUT]
{mypy_output[:4000]}

Interpret the mypy output. For each type error output:
{{"check_name":"linter_mypy_xxx", "severity":"...", "message":"..."}}
Return JSON array only."""
            try:
                result = self.llm.generate(prompt, temperature=0.2, max_tokens=2000)
                start, end = result.find("["), result.rfind("]") + 1
                if start != -1 and end != 0:
                    for item in json.loads(result[start:end]):
                        findings.append(Finding(**item, confidence=0.85))
            except Exception:
                pass

        return findings


# ─────────────────────────────────────────────
# NEW: Data Science Agent — statistics + data integrity
# ─────────────────────────────────────────────

class DatascienceAgent(BaseAgent):
    """Data science & statistics agent — modeling correctness, data quality."""

    def get_description(self) -> str:
        return "Statistical modeling, data integrity, overfitting detection"
    def get_domain(self) -> str:
        return "datascience"

    def inspect(self, files_context: str) -> List[Finding]:
        return _llm_inspect("datascience", """You are a data science auditor. Inspect:
1. Missing train/test split or data leakage
2. Overfitting indicators (no regularization, too many params)
3. NaN/Inf handling (missing check before division or log)
4. Feature scaling inconsistency
5. Statistical assumptions violations (normality, homoscedasticity)
6. ETL data integrity: missing primary key checks, row count validation
7. Numerical stability issues (softmax overflow, exp underflow)""", "data science", files_context, self.project_profile, self.llm)


# ─────────────────────────────────────────────
# NEW: Hardcode Agent — generic hardcoded value detection
# ─────────────────────────────────────────────

class HardcodeAgent(BaseAgent):
    """Hardcoded value detection agent — general-purpose, not just security."""

    def get_description(self) -> str:
        return "Hardcoded values, magic numbers, cross-file duplicate constants"
    def get_domain(self) -> str:
        return "hardcode"

    def inspect(self, files_context: str) -> List[Finding]:
        return _llm_inspect("hardcode", """You are a hardcoded value auditor. Inspect:
1. Magic numbers without named constants (e.g., timeout=30, threshold=0.8)
2. String literals repeated across files (e.g., API URLs, error messages)
3. Configuration values hardcoded in source instead of config/env
4. File paths, port numbers, hostnames embedded in code
5. Fake/test data that could leak to production (e.g., "test@example.com", admin/admin)""", "hardcode detection", files_context, self.project_profile, self.llm)


# ── Agent registry ──

LLM_AGENT_CLASSES = {
    "developer": DeveloperAgent,
    "architect": ArchitectAgent,
    "performance": PerformanceAgent,
    "devops": DevOpsAgent,
    "testing": TestAgent,
    "api": APIAgent,
    "dependency": DependencyAgent,
    "concurrency": ConcurrencyAgent,
    "linter": LinterAgent,
    "datascience": DatascienceAgent,
    "hardcode": HardcodeAgent,
}
