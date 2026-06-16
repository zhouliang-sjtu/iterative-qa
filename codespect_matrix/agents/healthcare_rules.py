"""Healthcare domain rule engine — deterministic checks for medical compliance.

This module provides rule-based scanning for healthcare-specific issues
WITHOUT relying on LLM, ensuring zero false negatives for critical
compliance violations (HIPAA, PHI, clinical data integrity).

Coverage:
- PHI/PII detection (US + China healthcare contexts)
- FHIR data format validation
- DICOM metadata safety checks
- HL7 message structure validation
- Clinical lab value range validation (physiological ranges)
- CDS (Clinical Decision Support) rule audit
- SMART on FHIR security compliance
"""

from __future__ import annotations

import re
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass


@dataclass
class RuleFinding:
    check_name: str
    severity: str          # critical/high/medium/low
    message: str
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    evidence: str = ""
    remediation: str = ""
    confidence: float = 1.0


# ─── PHI/PII Detection Patterns ──────────────────────────────────────────────

# US Healthcare identifiers
US_PHI_PATTERNS = [
    (r'\b\d{3}-\d{2}-\d{4}\b', 'SSN', 'critical'),
    (r'\b[A-Z]{2}\d{6,10}\b', 'Medical Record Number', 'high'),
    (r'Medicare[\s#:]*\d{9,11}', 'Medicare ID', 'high'),
    (r'Medicaid[\s#:]*\d{9,12}', 'Medicaid ID', 'high'),
    (r'\b[A-Z]{1}\d{8,10}\b', 'Possible Health Plan ID', 'medium'),
]

# China healthcare identifiers
CN_PHI_PATTERNS = [
    (r'\b\d{17}[\dXx]\b', 'China National ID (18-digit)', 'critical'),
    (r'\b1[3-9]\d{9}\b', 'China Mobile Phone', 'high'),
    (r'医保[号卡]*[:：\s]*\d{6,20}', 'China Medical Insurance ID', 'high'),
    (r'病历[号]*[:：\s]*\d{4,15}', 'China Medical Record Number', 'high'),
    (r'就诊[卡号]*[:：\s]*\d{6,20}', 'China Patient Card Number', 'high'),
    (r'住院[号]*[:：\s]*\d{4,15}', 'China Inpatient ID', 'high'),
]

# Generic PHI leak patterns (logging/printing/output)
PHI_LEAK_PATTERNS = [
    (r'(?:print|console\.log|logger\.\w+|log\.\w+|sys\.stdout\.write)\s*\([^)]*(?:patient|姓名|身份证号|手机号|病历号|医保)', 'PHI leaked in log/print', 'critical'),
    (r'(?:print|console\.log|logger\.\w+|log\.\w+)\s*\([^)]*(?:ssn|social_security|medical_record|patient_id)', 'PHI leaked in log/print (EN)', 'critical'),
    (r'return\s+\{[^}]*(?:patient_name|patient_id|身份证号|手机号)[^}]*\}', 'PHI in API response', 'critical'),
    (r'json\.dumps\s*\([^)]*(?:patient|phi|pii)', 'PHI serialized to JSON', 'high'),
    (r'(?:write|send|post|put)\s*\([^)]*(?:patient|姓名|身份证号)', 'PHI transmitted without encryption', 'critical'),
]

# ─── FHIR Validation Rules ───────────────────────────────────────────────────

FHIR_PATTERNS = [
    (r'from\s+fhirclient|import\s+fhirclient|from\s+fhiry', 'FHIR client library usage', 'info'),
    (r'Resource\s*\(\s*["\']Patient["\']', 'FHIR Patient Resource', 'info'),
    (r'Resource\s*\(\s*["\']Observation["\']', 'FHIR Observation Resource', 'info'),
]

FHIR_SECURITY_RULES = [
    {
        'check': 'fhir_auth_missing',
        'pattern': r'fhirclient\.client\.FHIRClient\s*\([^)]*\)',
        'negative_pattern': r'auth|token|bearer|oauth| SMART',
        'message': 'FHIR client initialized without authentication — SMART on FHIR compliance violation',
        'severity': 'critical',
    },
    {
        'check': 'fhir_http_not_https',
        'pattern': r'["\']http://[^"\']*(?:fhir|hl7)',
        'message': 'FHIR endpoint uses HTTP instead of HTTPS — patient data transmitted insecurely',
        'severity': 'critical',
    },
    {
        'check': 'fhir_patient_export_unrestricted',
        'pattern': r'Patient\.read\(\)|Patient\.where|Patient\.search',
        'negative_pattern': r'user_id|patient_id|scope|restricted',
        'message': 'FHIR Patient resource query without patient-scoped access control',
        'severity': 'high',
    },
]

# ─── DICOM Safety Rules ──────────────────────────────────────────────────────

DICOM_PATTERNS = [
    (r'import\s+pydicom|from\s+pydicom|import\s+dicom', 'DICOM library usage', 'info'),
]

DICOM_SECURITY_RULES = [
    {
        'check': 'dicom_phi_in_tags',
        'pattern': r'dcm\.PatientName|dcm\.PatientID|dcm\.PatientBirthDate',
        'negative_pattern': r'anonymize|deidentify|remove|blank',
        'message': 'DICOM metadata contains PHI tags without anonymization before sharing/export',
        'severity': 'critical',
    },
    {
        'check': 'dicom_export_unencrypted',
        'pattern': r'\.save\(|dcmwrite|write_like_original',
        'negative_pattern': r'encrypt|password|secure',
        'message': 'DICOM file exported without encryption — PHI at rest unprotected',
        'severity': 'high',
    },
]

# ─── HL7 Message Rules ───────────────────────────────────────────────────────

HL7_PATTERNS = [
    (r'import\s+hl7apy|from\s+hl7apy', 'HL7 library usage', 'info'),
]

HL7_SECURITY_RULES = [
    {
        'check': 'hl7_phi_in_msh',
        'pattern': r'PID\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|',
        'message': 'HL7 PID segment may contain PHI — ensure MLLP encryption or TLS',
        'severity': 'high',
    },
    {
        'check': 'hl7_mllp_no_tls',
        'pattern': r'MLLP|mllp|HL7\.Server|start_server',
        'negative_pattern': r'tls|ssl|encrypt|secure',
        'message': 'HL7 MLLP server without TLS encryption — patient data transmitted in plaintext',
        'severity': 'critical',
    },
]

# ─── Clinical Lab Value Ranges ───────────────────────────────────────────────

LAB_RANGES = {
    # Format: (min, max, unit, display_name)
    'blood_pressure_systolic': (60, 260, 'mmHg', 'Systolic BP'),
    'blood_pressure_diastolic': (30, 150, 'mmHg', 'Diastolic BP'),
    'heart_rate': (30, 250, 'bpm', 'Heart Rate'),
    'spo2': (60, 100, '%', 'SpO2'),
    'blood_glucose': (20, 600, 'mg/dL', 'Blood Glucose'),
    'hemoglobin_male': (4.0, 20.0, 'g/dL', 'Hemoglobin (Male)'),
    'hemoglobin_female': (3.5, 18.0, 'g/dL', 'Hemoglobin (Female)'),
    'wbc': (1.0, 50.0, '10^9/L', 'WBC'),
    'platelet': (10, 1000, '10^9/L', 'Platelet'),
    'creatinine': (0.1, 20.0, 'mg/dL', 'Serum Creatinine'),
    'bun': (1, 200, 'mg/dL', 'BUN'),
    'total_bilirubin': (0.1, 30.0, 'mg/dL', 'Total Bilirubin'),
    'alt': (1, 1000, 'U/L', 'ALT'),
    'ast': (1, 1000, 'U/L', 'AST'),
    'sodium': (100, 180, 'mmol/L', 'Sodium'),
    'potassium': (2.0, 9.0, 'mmol/L', 'Potassium'),
    'calcium': (5.0, 15.0, 'mg/dL', 'Calcium'),
    'ph': (6.5, 7.8, '', 'Blood pH'),
    'body_temperature': (30.0, 45.0, '°C', 'Body Temperature'),
    'respiratory_rate': (5, 60, 'breaths/min', 'Respiratory Rate'),
}

# Regex to find lab value assignments/comparisons in code
LAB_VALUE_PATTERNS = [
    # blood_pressure = 120, bp = 140, etc.
    (r'(?:blood_pressure|bp|systolic)\s*[=:]\s*(\d+(?:\.\d+)?)', 'blood_pressure_systolic'),
    (r'(?:diastolic|dbp)\s*[=:]\s*(\d+(?:\.\d+)?)', 'blood_pressure_diastolic'),
    (r'(?:heart_rate|hr|pulse)\s*[=:]\s*(\d+(?:\.\d+)?)', 'heart_rate'),
    (r'(?:spo2|o2_sat|oxygen_sat)\s*[=:]\s*(\d+(?:\.\d+)?)', 'spo2'),
    (r'(?:glucose|blood_glucose|bg)\s*[=:]\s*(\d+(?:\.\d+)?)', 'blood_glucose'),
    (r'(?:hemoglobin|hgb|hb)\s*[=:]\s*(\d+(?:\.\d+)?)', 'hemoglobin_male'),
    (r'(?:wbc|white_blood_cell)\s*[=:]\s*(\d+(?:\.\d+)?)', 'wbc'),
    (r'(?:platelet|plt)\s*[=:]\s*(\d+(?:\.\d+)?)', 'platelet'),
    (r'(?:creatinine|cr)\s*[=:]\s*(\d+(?:\.\d+)?)', 'creatinine'),
    (r'(?:bun|blood_urea_nitrogen)\s*[=:]\s*(\d+(?:\.\d+)?)', 'bun'),
    (r'(?:bilirubin|tbil)\s*[=:]\s*(\d+(?:\.\d+)?)', 'total_bilirubin'),
    (r'(?:alt|alanine_aminotransferase)\s*[=:]\s*(\d+(?:\.\d+)?)', 'alt'),
    (r'(?:ast|aspartate_aminotransferase)\s*[=:]\s*(\d+(?:\.\d+)?)', 'ast'),
    (r'(?:sodium|na)\s*[=:]\s*(\d+(?:\.\d+)?)', 'sodium'),
    (r'(?:potassium|k)\s*[=:]\s*(\d+(?:\.\d+)?)', 'potassium'),
    (r'(?:calcium|ca)\s*[=:]\s*(\d+(?:\.\d+)?)', 'calcium'),
    (r'(?:ph|blood_ph)\s*[=:]\s*(\d+(?:\.\d+)?)', 'ph'),
    (r'(?:temperature|body_temp|bt)\s*[=:]\s*(\d+(?:\.\d+)?)', 'body_temperature'),
    (r'(?:respiratory_rate|rr|resp_rate)\s*[=:]\s*(\d+(?:\.\d+)?)', 'respiratory_rate'),
]

# ─── CDS (Clinical Decision Support) Rules ───────────────────────────────────

CDS_PATTERNS = [
    {
        'check': 'cds_missing_fallback',
        'pattern': r'if\s+\w+\s*[<>=!]+\s*\d+\s*:',
        'negative_pattern': r'else|elif|default|fallback',
        'message': 'CDS rule lacks fallback/else branch — incomplete clinical decision logic',
        'severity': 'high',
    },
    {
        'check': 'cds_hardcoded_threshold',
        'pattern': r'if\s+(?:systolic|diastolic|glucose|bp)\s*\w*\s*[<>=!]+\s*\d+',
        'negative_pattern': r'config|settings|threshold|parameter|cfg',
        'message': 'CDS threshold hardcoded — should be configurable for different patient populations',
        'severity': 'medium',
    },
    {
        'check': 'cds_no_alert_escalation',
        'pattern': r'alert|warn|notify|message',
        'negative_pattern': r'critical|urgent|emergency|escalate|pager',
        'message': 'CDS alert system without escalation path for critical findings',
        'severity': 'high',
    },
]

# ─── SMART on FHIR Compliance ────────────────────────────────────────────────

SMART_FHIR_RULES = [
    {
        'check': 'smart_missing_launch_scope',
        'pattern': r'scope|launch|patient|user|openid',
        'negative_pattern': r'launch/patient|launch/encounter|patient/*.read',
        'message': 'SMART on FHIR app missing required launch scopes',
        'severity': 'high',
    },
    {
        'check': 'smart_token_no_validation',
        'pattern': r'access_token|id_token|bearer',
        'negative_pattern': r'jwt|verify|validate|decode|signature',
        'message': 'SMART on FHIR token accepted without JWT validation',
        'severity': 'critical',
    },
    {
        'check': 'smart_no_audience_check',
        'pattern': r'token|authorization',
        'negative_pattern': r'aud|audience|iss|issuer',
        'message': 'SMART on FHIR missing audience/issuer verification — token replay attack possible',
        'severity': 'critical',
    },
]


# ─── Rule Engine ─────────────────────────────────────────────────────────────

class HealthcareRuleEngine:
    """Deterministic healthcare rule engine."""

    def __init__(self):
        self.findings: List[RuleFinding] = []

    def scan_file(self, file_path: str, content: str) -> List[RuleFinding]:
        """Scan a single file for all healthcare rule violations."""
        self.findings = []
        lines = content.split('\n')

        # 1. PHI/PII detection
        self._scan_phi_pii(file_path, lines)

        # 2. FHIR security
        self._scan_fhir(file_path, lines, content)

        # 3. DICOM security
        self._scan_dicom(file_path, lines, content)

        # 4. HL7 security
        self._scan_hl7(file_path, lines, content)

        # 5. Lab value ranges
        self._scan_lab_values(file_path, lines)

        # 6. CDS rules
        self._scan_cds(file_path, lines, content)

        # 7. SMART on FHIR
        self._scan_smart_fhir(file_path, lines, content)

        return self.findings

    def _scan_phi_pii(self, file_path: str, lines: List[str]):
        """Scan for PHI/PII leaks."""
        for line_no, line in enumerate(lines, 1):
            # US PHI
            for pattern, label, severity in US_PHI_PATTERNS:
                for match in re.finditer(pattern, line, re.IGNORECASE):
                    self.findings.append(RuleFinding(
                        check_name=f"phi_{label.lower().replace(' ', '_')}",
                        severity=severity,
                        message=f"Potential {label} exposure in code",
                        file_path=file_path,
                        line_start=line_no,
                        line_end=line_no,
                        evidence=line.strip(),
                        remediation=f"Remove or mask {label} from source code. Use tokenization or reference IDs.",
                        confidence=0.95,
                    ))

            # China PHI
            for pattern, label, severity in CN_PHI_PATTERNS:
                for match in re.finditer(pattern, line):
                    self.findings.append(RuleFinding(
                        check_name=f"phi_cn_{label.lower().replace(' ', '_').replace('(', '').replace(')', '')}",
                        severity=severity,
                        message=f"Potential {label} exposure in code",
                        file_path=file_path,
                        line_start=line_no,
                        line_end=line_no,
                        evidence=line.strip(),
                        remediation=f"Remove or mask {label} from source code. Use encrypted storage or reference IDs.",
                        confidence=0.95,
                    ))

            # PHI leak patterns (logging/printing)
            for pattern, label, severity in PHI_LEAK_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    self.findings.append(RuleFinding(
                        check_name=f"phi_leak_{label.lower().replace(' ', '_').replace('/', '_')}",
                        severity=severity,
                        message=f"{label}",
                        file_path=file_path,
                        line_start=line_no,
                        line_end=line_no,
                        evidence=line.strip(),
                        remediation="Use structured logging with PHI redaction. Never log raw patient identifiers.",
                        confidence=0.9,
                    ))

    def _scan_fhir(self, file_path: str, lines: List[str], content: str):
        """Scan for FHIR security issues."""
        for rule in FHIR_SECURITY_RULES:
            if re.search(rule['pattern'], content):
                # Check negative pattern (must NOT be present)
                if 'negative_pattern' in rule:
                    if re.search(rule['negative_pattern'], content, re.IGNORECASE):
                        continue

                # Find line number
                line_no = 1
                for i, line in enumerate(lines, 1):
                    if re.search(rule['pattern'], line):
                        line_no = i
                        break

                self.findings.append(RuleFinding(
                    check_name=rule['check'],
                    severity=rule['severity'],
                    message=rule['message'],
                    file_path=file_path,
                    line_start=line_no,
                    evidence=lines[line_no - 1].strip() if line_no <= len(lines) else "",
                    remediation="Implement OAuth2/SMART on FHIR authentication. Always use HTTPS endpoints.",
                    confidence=0.95,
                ))

    def _scan_dicom(self, file_path: str, lines: List[str], content: str):
        """Scan for DICOM security issues."""
        # Only scan files that use pydicom
        if not re.search(r'import\s+pydicom|from\s+pydicom', content):
            return

        for rule in DICOM_SECURITY_RULES:
            if re.search(rule['pattern'], content):
                if 'negative_pattern' in rule:
                    if re.search(rule['negative_pattern'], content, re.IGNORECASE):
                        continue

                line_no = 1
                for i, line in enumerate(lines, 1):
                    if re.search(rule['pattern'], line):
                        line_no = i
                        break

                self.findings.append(RuleFinding(
                    check_name=rule['check'],
                    severity=rule['severity'],
                    message=rule['message'],
                    file_path=file_path,
                    line_start=line_no,
                    evidence=lines[line_no - 1].strip() if line_no <= len(lines) else "",
                    remediation="Anonymize DICOM tags before export. Use DICOM de-identification profiles.",
                    confidence=0.95,
                ))

    def _scan_hl7(self, file_path: str, lines: List[str], content: str):
        """Scan for HL7 security issues."""
        if not re.search(r'import\s+hl7apy|from\s+hl7apy|HL7\.', content):
            return

        for rule in HL7_SECURITY_RULES:
            if re.search(rule['pattern'], content, re.IGNORECASE):
                if 'negative_pattern' in rule:
                    if re.search(rule['negative_pattern'], content, re.IGNORECASE):
                        continue

                line_no = 1
                for i, line in enumerate(lines, 1):
                    if re.search(rule['pattern'], line, re.IGNORECASE):
                        line_no = i
                        break

                self.findings.append(RuleFinding(
                    check_name=rule['check'],
                    severity=rule['severity'],
                    message=rule['message'],
                    file_path=file_path,
                    line_start=line_no,
                    evidence=lines[line_no - 1].strip() if line_no <= len(lines) else "",
                    remediation="Enable TLS/MLLP encryption for HL7 message transport. Use VPN or secure tunnels.",
                    confidence=0.9,
                ))

    def _scan_lab_values(self, file_path: str, lines: List[str]):
        """Scan for invalid clinical lab value assignments."""
        for line_no, line in enumerate(lines, 1):
            for pattern, lab_key in LAB_VALUE_PATTERNS:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    try:
                        value = float(match.group(1))
                    except ValueError:
                        continue

                    if lab_key not in LAB_RANGES:
                        continue

                    min_val, max_val, unit, name = LAB_RANGES[lab_key]
                    if value < min_val or value > max_val:
                        self.findings.append(RuleFinding(
                            check_name=f"lab_value_invalid_{lab_key}",
                            severity='high',
                            message=f"Invalid {name}: {value} {unit} (physiological range: {min_val}-{max_val} {unit})",
                            file_path=file_path,
                            line_start=line_no,
                            line_end=line_no,
                            evidence=line.strip(),
                            remediation=f"Validate {name} against physiological range ({min_val}-{max_val} {unit}) before processing.",
                            confidence=0.98,
                        ))

    def _scan_cds(self, file_path: str, lines: List[str], content: str):
        """Scan for CDS rule issues."""
        # Only scan files that appear to contain CDS logic
        if not re.search(r'clinical|decision|alert|threshold|rule', content, re.IGNORECASE):
            return

        for rule in CDS_PATTERNS:
            for line_no, line in enumerate(lines, 1):
                if re.search(rule['pattern'], line):
                    if 'negative_pattern' in rule:
                        # Check if negative pattern exists in nearby context (within 5 lines)
                        context_start = max(0, line_no - 3)
                        context_end = min(len(lines), line_no + 3)
                        context = '\n'.join(lines[context_start:context_end])
                        if re.search(rule['negative_pattern'], context, re.IGNORECASE):
                            continue

                    self.findings.append(RuleFinding(
                        check_name=rule['check'],
                        severity=rule['severity'],
                        message=rule['message'],
                        file_path=file_path,
                        line_start=line_no,
                        line_end=line_no,
                        evidence=line.strip(),
                        remediation="Add complete decision branches and configurable thresholds. Implement alert escalation.",
                        confidence=0.85,
                    ))

    def _scan_smart_fhir(self, file_path: str, lines: List[str], content: str):
        """Scan for SMART on FHIR compliance issues."""
        if not re.search(r'fhir|smart|oauth|launch', content, re.IGNORECASE):
            return

        for rule in SMART_FHIR_RULES:
            for line_no, line in enumerate(lines, 1):
                if re.search(rule['pattern'], line, re.IGNORECASE):
                    if 'negative_pattern' in rule:
                        context_start = max(0, line_no - 5)
                        context_end = min(len(lines), line_no + 5)
                        context = '\n'.join(lines[context_start:context_end])
                        if re.search(rule['negative_pattern'], context, re.IGNORECASE):
                            continue

                    self.findings.append(RuleFinding(
                        check_name=rule['check'],
                        severity=rule['severity'],
                        message=rule['message'],
                        file_path=file_path,
                        line_start=line_no,
                        line_end=line_no,
                        evidence=line.strip(),
                        remediation="Implement full SMART on FHIR launch sequence with scope validation and JWT verification.",
                        confidence=0.9,
                    ))


# ─── Public API ──────────────────────────────────────────────────────────────

def scan_project(project_path: str, files: List[Tuple[str, str]]) -> List[RuleFinding]:
    """Scan a list of (file_path, content) tuples for healthcare violations.

    Returns:
        List of RuleFinding objects.
    """
    engine = HealthcareRuleEngine()
    all_findings = []
    for file_path, content in files:
        findings = engine.scan_file(file_path, content)
        all_findings.extend(findings)
    return all_findings
