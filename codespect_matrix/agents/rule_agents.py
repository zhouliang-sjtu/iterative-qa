"""Rule+LLM hybrid agents — core security/healthcare domains retain rule engines.

Hybrid mode: Rule engine does initial scan → LLM does reasoning/review/fix.
"""

from __future__ import annotations

import os
from typing import Dict, List, Any, TYPE_CHECKING

from .base import BaseAgent, AgentRole, Finding, AgentMessage, MessageType

if TYPE_CHECKING:
    from .bus import AgentCommunicationBus
    from .memory import ProjectMemory

try:
    from ..llm_service import LLMService, DEFAULT_ANALYSIS_TEMPERATURE
except ImportError:
    LLMService = None
    DEFAULT_ANALYSIS_TEMPERATURE = 0.2


def _load_rule_expert():
    """Lazy-load rule experts from perspectives module (pre-v1.0 legacy).
    
    Since v1.0 the legacy rule engine has been removed. Returns None-tuple
    so hybrid agents gracefully fall back to LLM-only mode.
    """
    return (None, None, None, None, None, None)


class RuleAgentMixin:
    """Mixin providing rule_scan() + LLM fallback for hybrid agents."""

    def _rule_scan(self, expert_class, project_features: Dict) -> List[Finding]:
        """Run rule-based expert scan and convert to Finding list."""
        if expert_class is None:
            return []
        _, _, _, _, _, RuleValidationResult = _load_rule_expert()
        try:
            expert = expert_class()
            rules_results = expert.validate(project_features)
            findings = []
            for r in rules_results:
                f = Finding(
                    check_name=r.check_name,
                    severity=r.severity,
                    message=r.message,
                    evidence="",
                    remediation=r.remediation or "",
                    confidence=0.95 if r.severity in ("critical", "high") else 0.7,
                )
                findings.append(f)
            return findings
        except Exception:
            return []

    def _llm_inspect(self, files_context: str, domain: str) -> List[Finding]:
        """LLM-only inspection fallback when legacy rule engine is unavailable.
        
        Since v1.0 the rule engine has been removed. Hybrid agents use
        this method to perform domain-specific LLM analysis directly.
        """
        if not self.llm or not files_context:
            return []
        system_prompts = {
            "security": "Find security vulnerabilities: eval injection, weak crypto, secret leaks, unsafe deserialization.",
            "healthcare": "Find healthcare compliance issues: HIPAA, patient data exposure, medical device validation.",
            "phi": "Find PHI/PII leaks: patient IDs, names, phone numbers, addresses in logs/print/output.",
            "compliance": "Find compliance gaps: missing licenses, missing audit trails, GDPR issues.",
            "medical_data": "Find medical data issues: invalid biometric ranges, ICD coding errors, data integrity.",
        }
        prompt = system_prompts.get(domain, f"Find {domain}-related code issues")
        try:
            response = self.llm.generate(
                f"{prompt}\n\nCode to analyze:\n{files_context[:4000]}",
                temperature=DEFAULT_ANALYSIS_TEMPERATURE,
                max_tokens=600,
            )
            f = Finding(
                check_name=f"{domain}_llm_scan",
                severity="medium",
                message=f"LLM analysis for {domain}: {response[:200]}",
                confidence=0.6,
            )
            return [f]
        except Exception:
            return []


class SecurityAgent(BaseAgent, RuleAgentMixin):
    """Security audit agent — rule engine + LLM deep analysis."""

    def get_description(self) -> str:
        return "Vulnerability scanning, crypto strength audit, secret leak detection"
    def get_domain(self) -> str:
        return "security"

    def inspect(self, files_context: str) -> List[Finding]:
        SecurityExpert = _load_rule_expert()[0]
        if SecurityExpert is None:
            return self._llm_inspect(files_context, "security")
        findings = self._rule_scan(SecurityExpert, self.project_profile)

        # LLM deep analysis for critical/high findings
        if self.llm and findings:
            for f in findings:
                if f.severity in ("critical", "high"):
                    try:
                        prompt = f"""As a security expert, review this finding:
Check: {f.check_name}
Severity: {f.severity}
Description: {f.message}
Suggested fix: {f.remediation}

Evaluate:
1. Is this a real vulnerability or false positive?
2. If real, what is the attack scenario?
3. What is the most effective fix?

Return brief conclusion only."""
                        analysis = self.llm.generate(
                            prompt, temperature=DEFAULT_ANALYSIS_TEMPERATURE,
                            max_tokens=300,
                        )
                        f.evidence = analysis
                        f.confidence = 0.98
                    except Exception:
                        pass
        return findings

    def review(self, finding: Finding) -> Dict[str, Any]:
        if finding.check_name.startswith("security"):
            verdict = "adjusted"
            comment = "Security risk confirmed"
            if finding.severity == "low":
                comment = "Low security risk, can downgrade"
            return {
                "verdict": verdict, "confidence": 0.9, "comment": comment,
                "adjusted_severity": finding.severity,
            }
        return super().review(finding)


class HealthcareAgent(BaseAgent, RuleAgentMixin):
    """Healthcare compliance agent — rule engine + LLM context reasoning."""

    def get_description(self) -> str:
        return "Healthcare compliance, HIPAA audit, patient data protection"
    def get_domain(self) -> str:
        return "healthcare"

    def inspect(self, files_context: str) -> List[Finding]:
        HealthcareExpert = _load_rule_expert()[1]
        if HealthcareExpert is None:
            return self._llm_inspect(files_context, "healthcare")
        return self._rule_scan(HealthcareExpert, self.project_profile)

    def review(self, finding: Finding) -> Dict[str, Any]:
        if "hipaa" in finding.check_name.lower() or "phi" in finding.check_name.lower():
            return {
                "verdict": "confirmed", "confidence": 0.95,
                "comment": "Healthcare compliance issue — no exceptions",
                "adjusted_severity": finding.severity,
            }
        return super().review(finding)


class PHIAgent(BaseAgent, RuleAgentMixin):
    """PHI detection agent — rule detection + LLM confirmation."""

    def get_description(self) -> str:
        return "Protected Health Information detection, data masking verification, PII scanning"
    def get_domain(self) -> str:
        return "phi_protection"

    def inspect(self, files_context: str) -> List[Finding]:
        PHIInspectExpert = _load_rule_expert()[3]
        if PHIInspectExpert is None:
            return self._llm_inspect(files_context, "phi")
        return self._rule_scan(PHIInspectExpert, self.project_profile)

    def review(self, finding: Finding) -> Dict[str, Any]:
        if "phi" in finding.check_name.lower() or "id_card" in finding.check_name.lower():
            return {
                "verdict": "confirmed", "confidence": 1.0,
                "comment": "PHI issue — zero tolerance, must fix immediately",
                "adjusted_severity": "critical",
            }
        return super().review(finding)


class ComplianceAgent(BaseAgent, RuleAgentMixin):
    """Compliance audit agent."""

    def get_description(self) -> str:
        return "GDPR, ISO27001, industry-standard compliance auditing"
    def get_domain(self) -> str:
        return "compliance"

    def inspect(self, files_context: str) -> List[Finding]:
        ComplianceExpert = _load_rule_expert()[2]
        if ComplianceExpert is None:
            return self._llm_inspect(files_context, "compliance")
        return self._rule_scan(ComplianceExpert, self.project_profile)


class MedicalDataAgent(BaseAgent, RuleAgentMixin):
    """Medical data validation agent."""

    def get_description(self) -> str:
        return "Medical data integrity, format validation, clinical trial compliance"
    def get_domain(self) -> str:
        return "medical_data"

    def inspect(self, files_context: str) -> List[Finding]:
        MedicalDataValidatorExpert = _load_rule_expert()[4]
        if MedicalDataValidatorExpert is None:
            return self._llm_inspect(files_context, "medical_data")
        return self._rule_scan(MedicalDataValidatorExpert, self.project_profile)
