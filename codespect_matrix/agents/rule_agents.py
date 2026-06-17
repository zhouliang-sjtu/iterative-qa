"""Rule+LLM hybrid agents — core security/healthcare domains retain rule engines.

Hybrid mode: Rule engine does initial scan → LLM does reasoning/review/fix.
"""

from __future__ import annotations

import os
from typing import Dict, List, Any, TYPE_CHECKING

from .base import BaseAgent, AgentRole, Finding, AgentMessage, MessageType
from .healthcare_rules import HealthcareRuleEngine, RuleFinding

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
        # Use deterministic healthcare rule engine for security rules
        all_rule_findings = _scan_with_healthcare_rules(files_context)
        security_check_prefixes = (
            'sql_injection', 'unsafe_', 'hardcoded_', 'aws_credentials',
            'os_system', 'shell_true', 'eval_usage', 'exec_usage',
            'path_traversal', 'weak_hash', 'ssl_verify',
            'insecure_cipher', 'unvalidated_',
            'xss_', 'xxe_', 'ssrf_', 'ldap_', 'ssti_',
            'weak_random', 'insecure_temp', 'insecure_deserialization',
            'error_suppression', 'timeout_missing', 'resource_leak',
            'race_condition', 'magic_number', 'float_equality',
        )
        findings = [f for f in all_rule_findings
                    if any(f.check_name.startswith(p) for p in security_check_prefixes)]
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


def _convert_rule_finding(rf: RuleFinding) -> Finding:
    """Convert RuleFinding from healthcare_rules to BaseAgent Finding."""
    return Finding(
        check_name=rf.check_name,
        severity=rf.severity,
        message=rf.message,
        file_path=rf.file_path,
        line_start=rf.line_start,
        line_end=rf.line_end,
        evidence=rf.evidence,
        remediation=rf.remediation,
        confidence=rf.confidence,
    )


def _scan_with_healthcare_rules(files_context: str) -> List[Finding]:
    """Use the deterministic healthcare rule engine to scan files."""
    engine = HealthcareRuleEngine()
    findings = []

    # Parse files_context into (file_path, content) pairs
    # files_context format: "=== FILE: path ===\ncontent"
    import re as _re
    file_blocks = _re.split(r'\n=== FILE: ', files_context)
    for block in file_blocks[1:]:  # skip empty first
        if '\n' not in block:
            continue
        header, content = block.split('\n', 1)
        file_path = header.strip().rstrip(' ===')
        rf_list = engine.scan_file(file_path, content)
        for rf in rf_list:
            findings.append(_convert_rule_finding(rf))

    return findings


class HealthcareAgent(BaseAgent, RuleAgentMixin):
    """Healthcare compliance agent — deterministic rule engine + LLM deep analysis."""

    def get_description(self) -> str:
        return "Healthcare compliance, HIPAA audit, patient data protection (rule-based + LLM)"
    def get_domain(self) -> str:
        return "healthcare"

    def inspect(self, files_context: str) -> List[Finding]:
        # Use deterministic healthcare rule engine first
        findings = _scan_with_healthcare_rules(files_context)

        # Filter to healthcare-specific findings
        healthcare_checks = {
            'phi_', 'fhir_', 'dicom_', 'hl7_', 'lab_value_', 'cds_',
            'smart_', 'hipaa', 'medical', 'patient', 'clinical',
        }
        filtered = [f for f in findings if any(f.check_name.startswith(c) or c in f.check_name.lower() for c in healthcare_checks)]

        # LLM deep analysis for critical/high findings without file location
        if self.llm and filtered:
            for f in filtered:
                if f.severity in ("critical", "high") and not f.evidence:
                    try:
                        prompt = f"""As a healthcare compliance expert, review this issue:
Check: {f.check_name}
Severity: {f.severity}
Description: {f.message}

Evaluate:
1. Is this a real HIPAA/compliance violation?
2. What is the specific regulatory requirement violated?
3. What is the most effective remediation?

Return brief conclusion only."""
                        analysis = self.llm.generate(
                            prompt, temperature=DEFAULT_ANALYSIS_TEMPERATURE,
                            max_tokens=300,
                        )
                        f.evidence = analysis
                        f.confidence = 0.98
                    except Exception:
                        pass

        return filtered

    def review(self, finding: Finding) -> Dict[str, Any]:
        if "hipaa" in finding.check_name.lower() or "phi" in finding.check_name.lower():
            return {
                "verdict": "confirmed", "confidence": 0.95,
                "comment": "Healthcare compliance issue — no exceptions",
                "adjusted_severity": finding.severity,
            }
        return super().review(finding)


class PHIAgent(BaseAgent, RuleAgentMixin):
    """PHI detection agent — deterministic rule engine for PHI/PII."""

    def get_description(self) -> str:
        return "Protected Health Information detection, data masking verification, PII scanning (rule-based)"
    def get_domain(self) -> str:
        return "phi_protection"

    def inspect(self, files_context: str) -> List[Finding]:
        findings = _scan_with_healthcare_rules(files_context)
        # Filter to PHI-specific findings
        phi_findings = [f for f in findings if f.check_name.startswith('phi_') or f.check_name.startswith('phi_leak_')]

        # Raise severity for all PHI findings to critical
        for f in phi_findings:
            f.severity = "critical"
            f.confidence = 1.0

        return phi_findings

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
    """Medical data validation agent — lab values, biometrics, clinical data integrity."""

    def get_description(self) -> str:
        return "Medical data integrity, format validation, clinical trial compliance (rule-based)"
    def get_domain(self) -> str:
        return "medical_data"

    def inspect(self, files_context: str) -> List[Finding]:
        findings = _scan_with_healthcare_rules(files_context)
        # Filter to lab value and clinical data findings
        medical_checks = {'lab_value_', 'cds_', 'dicom_', 'hl7_'}
        return [f for f in findings if any(f.check_name.startswith(c) for c in medical_checks)]


class FHIRAgent(BaseAgent, RuleAgentMixin):
    """FHIR data format and security compliance agent."""

    def get_description(self) -> str:
        return "FHIR Resource validation, SMART on FHIR compliance, endpoint security"
    def get_domain(self) -> str:
        return "fhir"

    def inspect(self, files_context: str) -> List[Finding]:
        findings = _scan_with_healthcare_rules(files_context)
        return [f for f in findings if f.check_name.startswith('fhir_') or f.check_name.startswith('smart_')]

    def review(self, finding: Finding) -> Dict[str, Any]:
        if "fhir" in finding.check_name.lower() or "smart" in finding.check_name.lower():
            return {
                "verdict": "confirmed", "confidence": 0.95,
                "comment": "FHIR/SMART compliance issue — interoperability and security risk",
                "adjusted_severity": finding.severity,
            }
        return super().review(finding)


class DICOMAgent(BaseAgent, RuleAgentMixin):
    """DICOM metadata and security agent."""

    def get_description(self) -> str:
        return "DICOM metadata PHI detection, anonymization verification, encryption audit"
    def get_domain(self) -> str:
        return "dicom"

    def inspect(self, files_context: str) -> List[Finding]:
        findings = _scan_with_healthcare_rules(files_context)
        return [f for f in findings if f.check_name.startswith('dicom_')]

    def review(self, finding: Finding) -> Dict[str, Any]:
        if "dicom" in finding.check_name.lower():
            return {
                "verdict": "confirmed", "confidence": 1.0,
                "comment": "DICOM PHI issue — patient imaging data at risk",
                "adjusted_severity": "critical",
            }
        return super().review(finding)


class HL7Agent(BaseAgent, RuleAgentMixin):
    """HL7 message security and format agent."""

    def get_description(self) -> str:
        return "HL7 message structure validation, MLLP encryption, PHI segment audit"
    def get_domain(self) -> str:
        return "hl7"

    def inspect(self, files_context: str) -> List[Finding]:
        findings = _scan_with_healthcare_rules(files_context)
        return [f for f in findings if f.check_name.startswith('hl7_')]


class CDSRulesAgent(BaseAgent, RuleAgentMixin):
    """Clinical Decision Support rule audit agent."""

    def get_description(self) -> str:
        return "CDS rule completeness, threshold configurability, alert escalation audit"
    def get_domain(self) -> str:
        return "cds"

    def inspect(self, files_context: str) -> List[Finding]:
        findings = _scan_with_healthcare_rules(files_context)
        return [f for f in findings if f.check_name.startswith('cds_')]
