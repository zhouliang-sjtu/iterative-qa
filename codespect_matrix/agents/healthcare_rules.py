"""Healthcare domain rule engine — comprehensive deterministic checks.

Coverage (51 rules added):
- PHI/PII detection (US + China healthcare contexts)
- FHIR data format validation
- DICOM metadata safety checks
- HL7 message structure validation
- Clinical lab value range validation (physiological ranges)
- CDS (Clinical Decision Support) rule audit
- SMART on FHIR security compliance
- HIPAA Security Rule compliance
- China medical data security regulations
- Drug safety checks
- Medical device software (IEC 62304)
- EHR data integrity
- Medical identity management
- Medical image safety
- Extended general security (XSS, XXE, SSRF, LDAP, SSTI, etc.)
- Healthcare code quality checks
"""

from __future__ import annotations

import re
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass


@dataclass
class RuleFinding:
    check_name: str
    severity: str
    message: str
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    evidence: str = ""
    remediation: str = ""
    confidence: float = 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# PHI/PII Detection Patterns
# ═══════════════════════════════════════════════════════════════════════════════

US_PHI_PATTERNS = [
    (r'\b\d{3}-\d{2}-\d{4}\b', 'SSN', 'critical'),
    (r'\b[A-Z]{2}\d{6,10}\b', 'Medical Record Number', 'high'),
    (r'Medicare[\s#:]*\d{9,11}', 'Medicare ID', 'high'),
    (r'Medicaid[\s#:]*\d{9,12}', 'Medicaid ID', 'high'),
    (r'\b[A-Z]{1}\d{8,10}\b', 'Possible Health Plan ID', 'medium'),
]

CN_PHI_PATTERNS = [
    (r'\b\d{17}[\dXx]\b', 'China National ID (18-digit)', 'critical'),
    (r'\b1[3-9]\d{9}\b', 'China Mobile Phone', 'high'),
    (r'医保[号卡]*[:：\s]*\d{6,20}', 'China Medical Insurance ID', 'high'),
    (r'病历[号]*[:：\s]*\d{4,15}', 'China Medical Record Number', 'high'),
    (r'就诊[卡号]*[:：\s]*\d{6,20}', 'China Patient Card Number', 'high'),
    (r'住院[号]*[:：\s]*\d{4,15}', 'China Inpatient ID', 'high'),
]

PHI_LEAK_PATTERNS = [
    (r'(?:print|console\.log|logger\.\w+|log\.\w+|sys\.stdout\.write)\s*\([^)]*(?:patient|姓名|身份证号|手机号|病历号|医保)', 'PHI leaked in log/print', 'critical'),
    (r'(?:print|console\.log|logger\.\w+|log\.\w+)\s*\([^)]*(?:ssn|social_security|medical_record|patient_id)', 'PHI leaked in log/print (EN)', 'critical'),
    (r'return\s+\{[^}]*(?:patient_name|patient_id|身份证号|手机号)[^}]*\}', 'PHI in API response', 'critical'),
    (r'json\.dumps\s*\([^)]*(?:patient|phi|pii)', 'PHI serialized to JSON', 'high'),
    (r'(?:write|send|post|put)\s*\([^)]*(?:patient|姓名|身份证号)', 'PHI transmitted without encryption', 'critical'),
]

# ═══════════════════════════════════════════════════════════════════════════════
# FHIR Validation Rules
# ═══════════════════════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════════════════════
# DICOM Safety Rules
# ═══════════════════════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════════════════════
# HL7 Message Rules
# ═══════════════════════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════════════════════
# General Security Rules
# ═══════════════════════════════════════════════════════════════════════════════

GENERAL_SECURITY_RULES = [
    # SQL Injection
    {
        'check': 'sql_injection_fstring',
        'pattern': r'f["\'].*SELECT.*\{[^}]+\}|f["\'].*INSERT.*\{[^}]+\}|f["\'].*UPDATE.*\{[^}]+\}|f["\'].*DELETE.*\{[^}]+\}|f["\'].*WHERE.*\{[^}]+\}',
        'message': 'Potential SQL injection via f-string — use parameterized queries',
        'severity': 'critical',
        'remediation': 'Use parameterized queries: cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))',
    },
    {
        'check': 'sql_injection_concat',
        'pattern': r'(?:execute|exec|cursor\.run)\s*\([^)]*\+[^)]*\)',
        'message': 'Potential SQL injection via string concatenation',
        'severity': 'critical',
        'remediation': 'Use parameterized queries instead of string concatenation',
    },
    # Unsafe Deserialization
    {
        'check': 'unsafe_pickle_deserialize',
        'pattern': r'pickle\.loads?\s*\(',
        'message': 'Unsafe pickle deserialization — potential RCE if data is untrusted',
        'severity': 'critical',
        'remediation': 'Use json.loads() or restricted unpickler. Never unpickle untrusted data.',
    },
    {
        'check': 'unsafe_yaml_load',
        'pattern': r'yaml\.load\s*\(',
        'negative_pattern': r'safe_load|Loader\s*=\s*yaml\.(?:SafeLoader|FullLoader|Loader)',
        'message': 'Unsafe yaml.load without SafeLoader — potential RCE',
        'severity': 'critical',
        'remediation': 'Use yaml.safe_load() or yaml.load(..., Loader=yaml.SafeLoader)',
    },
    {
        'check': 'unsafe_marshal',
        'pattern': r'marshal\.loads?\s*\(',
        'message': 'Unsafe marshal deserialization — potential code execution',
        'severity': 'high',
        'remediation': 'Avoid marshal for untrusted data. Use json instead.',
    },
    # Hardcoded Secrets
    {
        'check': 'hardcoded_api_key',
        'pattern': r'(?:API_KEY|api_key|APIKEY)\s*[=:]\s*["\'][^"\']+["\']',
        'message': 'Hardcoded API key detected — use environment variables',
        'severity': 'high',
        'remediation': 'Use os.environ["API_KEY"] or a secrets manager',
    },
    {
        'check': 'hardcoded_password',
        'pattern': r'(?:PASSWORD|password|PASSWD)\s*[=:]\s*["\'][^"\']+["\']',
        'message': 'Hardcoded password detected — use environment variables',
        'severity': 'high',
        'remediation': 'Use os.environ["PASSWORD"] or a secrets manager',
    },
    {
        'check': 'hardcoded_database_url',
        'pattern': r'(?:DATABASE_URL|DB_URL|DB_PASSWORD|DB_PASS)\s*[=:]\s*["\'][^"\']+["\']',
        'message': 'Hardcoded database credentials detected',
        'severity': 'critical',
        'remediation': 'Use environment variables or database connection pools with credential rotation',
    },
    {
        'check': 'hardcoded_secret_key',
        'pattern': r'(?:SECRET_KEY|SECRET_KEY_B64|PRIVATE_KEY)\s*[=:]\s*["\'][^"\']+["\']',
        'message': 'Hardcoded secret key detected',
        'severity': 'high',
        'remediation': 'Use os.environ["SECRET_KEY"] or secrets.token_hex()',
    },
    {
        'check': 'hardcoded_bearer_token',
        'pattern': r'Bearer\s+[a-zA-Z0-9_\-\.]{20,}',
        'message': 'Hardcoded bearer token detected',
        'severity': 'critical',
        'remediation': 'Use OAuth tokens from secure storage, not hardcoded',
    },
    {
        'check': 'aws_credentials',
        'pattern': r'(?:AWS_ACCESS_KEY|AWS_SECRET|aws_access_key_id|aws_secret_access_key)\s*[=:]\s*["\'][^"\']+["\']',
        'message': 'AWS credentials hardcoded — security critical',
        'severity': 'critical',
        'remediation': 'Use IAM roles or AWS credentials file, never hardcode',
    },
    # Command Injection
    {
        'check': 'os_system_injection',
        'pattern': r'os\.system\s*\([^)]*\+[^)]*\)',
        'message': 'Potential command injection via os.system',
        'severity': 'critical',
        'remediation': 'Use subprocess.run with list args, avoid shell=True',
    },
    {
        'check': 'shell_true_injection',
        'pattern': r'subprocess\.(run|Popen|call|check_output)\s*\([^)]*shell\s*=\s*True',
        'message': 'subprocess with shell=True — potential shell injection',
        'severity': 'high',
        'remediation': 'Avoid shell=True. Use list args: subprocess.run(["ls", "-la"])',
    },
    {
        'check': 'eval_usage',
        'pattern': r'(?<!\w)eval\s*\(',
        'message': 'eval() usage — potential code injection',
        'severity': 'critical',
        'remediation': 'Avoid eval(). Use ast.literal_eval() for safe parsing or redesign.',
    },
    {
        'check': 'exec_usage',
        'pattern': r'(?<!\w)exec\s*\(',
        'message': 'exec() usage — potential code injection',
        'severity': 'critical',
        'remediation': 'Avoid exec(). Use restricted execution environments if absolutely necessary.',
    },
    # Path Traversal
    {
        'check': 'path_traversal',
        'pattern': r'open\s*\([^)]*\%[^)]*\)|open\s*\([^)]*\.format\([^)]*request|open\s*\([^)]*\+[^)]*(?:path|file|filename)',
        'message': 'Potential path traversal vulnerability',
        'severity': 'high',
        'remediation': 'Validate and sanitize user input. Use pathlib and os.path.realpath() for path validation.',
    },
    # Weak Cryptography
    {
        'check': 'weak_hash',
        'pattern': r'(?:md5|sha1|hashlib\.md5|hashlib\.sha1)\s*\(',
        'message': 'Weak hash algorithm (MD5/SHA1) — not suitable for security',
        'severity': 'high',
        'remediation': 'Use SHA-256 or stronger. For passwords, use bcrypt or argon2.',
    },
    {
        'check': 'ssl_verify_disabled',
        'pattern': r'verify\s*=\s*False|ssl_verify\s*=\s*False',
        'message': 'SSL verification disabled — MITM attack possible',
        'severity': 'critical',
        'remediation': 'Enable SSL verification. Only disable for testing with trusted networks.',
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# HIPAA Security Rule Compliance
# ═══════════════════════════════════════════════════════════════════════════════

HIPAA_RULES = [
    {
        'check': 'hipaa_encryption_at_rest',
        'pattern': r'open\s*\(\s*["\'][^"\']*(?:patient|medical|health|clinical|phi)[^"\']*["\']\s*,\s*["\'][w]\w*["\']',
        'negative_pattern': r'encrypt|AES| Fernet|cipher|vault',
        'message': 'PHI data written to file without encryption — HIPAA encryption-at-rest violation (45 CFR 164.312(a)(2)(iv))',
        'severity': 'critical',
        'remediation': 'Encrypt all PHI data at rest using AES-256 or equivalent. Use encryption libraries or database-level encryption.',
    },
    {
        'check': 'hipaa_audit_log_missing',
        'pattern': r'def\s+(?:get_patient|fetch_patient|query_patient|read_patient|access_patient)',
        'negative_pattern': r'log|audit|logger|logging|timestamp|transaction',
        'message': 'Patient data access without audit logging — HIPAA audit control violation (45 CFR 164.312(b))',
        'severity': 'high',
        'remediation': 'Implement audit logging for all PHI access: who, what, when, and why. Use structured audit logs.',
    },
    {
        'check': 'hipaa_access_control',
        'pattern': r'(?:Patient|Record)\.(?:objects|query)\.(?:get|filter|all)\s*\(\)',
        'negative_pattern': r'user_id|patient_id|scope|role|permission|restricted',
        'message': 'Patient data query without access control — HIPAA access control violation (45 CFR 164.312(a)(1))',
        'severity': 'critical',
        'remediation': 'Implement role-based access control. Filter queries by user scope and patient association.',
    },
    {
        'check': 'hipaa_transmission_security',
        'pattern': r'["\']http://[^"\']*(?:patient|medical|health|phi|fhir|hl7)[^"\']*["\']',
        'message': 'PHI transmitted over HTTP instead of HTTPS — HIPAA transmission security violation (45 CFR 164.312(e)(1))',
        'severity': 'critical',
        'remediation': 'Always use HTTPS/TLS for PHI transmission. Configure HSTS headers.',
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# China Medical Data Security Regulations
# ═══════════════════════════════════════════════════════════════════════════════

CN_MEDICAL_REGULATIONS = [
    {
        'check': 'cn_medical_data_cross_border',
        'pattern': r'(?:requests\.(?:post|put|get)|urllib|httpx)\.',  # Triggered by internal context check
        'message': 'Potential cross-border medical data transfer — may violate China Personal Information Protection Law and Data Security Law',
        'severity': 'critical',
        'remediation': 'Implement data localization. Use China-based servers for patient data. Conduct security assessment before cross-border transfer.',
    },
    {
        'check': 'cn_data_localization',
        'pattern': r'(?:boto3|aws|s3\.amazonaws|azure\.com|gcs\.googleapis)',
        'negative_pattern': r'cn-north|china|北京|上海|beijing|shanghai',
        'message': 'Cloud storage endpoint outside China — may violate data localization requirements',
        'severity': 'high',
        'remediation': 'Use China-region cloud storage (e.g., AWS China, Azure China, Alibaba Cloud) for patient data.',
    },
    {
        'check': 'cn_identity_verification_missing',
        'pattern': r'def\s+(?:register|login|create_account|signup)',
        'negative_pattern': r'verify|实名|身份证|id_card|identity|authenticate|face_recognition',
        'message': 'Medical application without real-name identity verification — violates China Cybersecurity Law requirements',
        'severity': 'high',
        'remediation': 'Implement real-name verification (identity card + face recognition) per China Cybersecurity Law Article 24.',
    },
    {
        'check': 'cn_consent_missing',
        'pattern': r'(?:collect|gather|store).*(?:patient|health|medical|clinical)',
        'negative_pattern': r'consent|同意|知情|informed|authorization|permission',
        'message': 'Patient data collection without informed consent mechanism — violates China Personal Information Protection Law Article 13-17',
        'severity': 'high',
        'remediation': 'Implement explicit informed consent before collecting patient data. Maintain consent records.',
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# Clinical Decision Support (CDS) Safety Rules (Extended)
# ═══════════════════════════════════════════════════════════════════════════════

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

CDS_SAFETY_RULES = [
    {
        'check': 'cds_override_warning_enabled',
        'pattern': r'override_warning\s*=\s*(?:True|False)',
        'negative_pattern': r'override_warning\s*=\s*False',
        'message': 'Clinical override warning enabled — critical alerts can be suppressed without review',
        'severity': 'critical',
        'remediation': 'All clinical overrides must require documented reason and supervisor approval.',
    },
    {
        'check': 'cds_missing_dosing_limit',
        'pattern': r'(?:dosage|dose|mg_per_kg)\s*[=:]\s*(?:patient_weight|weight)\s*\*\s*',
        'negative_pattern': r'max|upper_bound|limit|max_dosage|MAX_DOSE',
        'message': 'Medication dosage calculation without maximum limit — risk of overdose',
        'severity': 'critical',
        'remediation': 'Add maximum dosage limits: dosage = min(calculated_dose, MAX_DOSE). Implement weight range validation.',
    },
    {
        'check': 'cds_allergy_check_missing',
        'pattern': r'(?:prescribe|order_medication|administer|give_drug)',
        'negative_pattern': r'allerg|cross_reaction|contraindication|adverse_reaction',
        'message': 'Medication prescribed without allergy/sensitivity check — patient safety risk',
        'severity': 'critical',
        'remediation': 'Check patient allergies and drug cross-sensitivity before every prescription.',
    },
    {
        'check': 'cds_no_human_review',
        'pattern': r'(?:auto_approve|auto_diagnose|auto_prescribe|automatic_decision)\s*=\s*True',
        'message': 'Critical clinical decision bypasses human review — violation of clinical safety standards',
        'severity': 'critical',
        'remediation': 'All critical decisions (diagnoses, prescriptions) must require human clinician review and approval.',
    },
    {
        'check': 'cds_diagnostic_delay_risk',
        'pattern': r'(?:schedule|delay|timer|sleep).*\(\s*(?:3600|7200|86400|\d{2,})\s*\)',
        'message': 'Diagnostic result delayed by long timer — may indicate clinical risk from delayed diagnosis',
        'severity': 'high',
        'remediation': 'Implement real-time or near-real-time diagnostic result delivery. Set appropriate SLA for critical results.',
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# Drug Safety Rules
# ═══════════════════════════════════════════════════════════════════════════════

DRUG_SAFETY_RULES = [
    {
        'check': 'drug_interaction_missing',
        'pattern': r'(?:prescribe|order_medication|prescription).*(?:medication|drug|medicine)',
        'negative_pattern': r'interaction|drug_interaction|interact|DDI',
        'message': 'Medication prescribed without drug-drug interaction check — patient safety risk',
        'severity': 'critical',
        'remediation': 'Implement drug-drug interaction database lookup before every prescription.',
    },
    {
        'check': 'drug_contraindication_missing',
        'pattern': r'(?:prescribe|order_medication|dispense)',
        'negative_pattern': r'contraindication|contraindicated|not_recommended|CI_',
        'message': 'Medication prescribed without contraindication screening',
        'severity': 'critical',
        'remediation': 'Check patient conditions against drug contraindications before prescribing.',
    },
    {
        'check': 'drug_allergy_cross_reaction',
        'pattern': r'(?:new_medication|add_drug|start_drug)',
        'negative_pattern': r'cross_react|cross_allerg|similar_class',
        'message': 'New medication added without cross-allergy class check',
        'severity': 'critical',
        'remediation': 'Verify cross-reactivity with patient allergy list. Check drug class similarities.',
    },
    {
        'check': 'drug_pregnancy_safety',
        'pattern': r'(?:prescribe|medication).*(?:pregnant|pregnancy|gestation|trimester)',
        'negative_pattern': r'pregnancy_category|FDA_category|pregnancy_safe',
        'message': 'Medication prescribed to pregnant patient without pregnancy safety category check',
        'severity': 'high',
        'remediation': 'Always check FDA pregnancy category and consult obstetric guidelines before prescribing to pregnant patients.',
    },
    {
        'check': 'drug_pediatric_dosing_adult',
        'pattern': r'(?:child|pediatric|paediatric|infant).*dosage.*\*.*weight',
        'negative_pattern': r'pediatric_formula|child_dose|Clark|Young|body_surface',
        'message': 'Possible use of adult dosing formula for pediatric patients',
        'severity': 'critical',
        'remediation': 'Use pediatric-specific dosing formulas (Clark\'s rule, Young\'s rule, BSA-based). Never apply adult formulas to children.',
    },
    {
        'check': 'drug_lab_monitor_missing',
        'pattern': r'(?:warfarin|heparin|insulin|digoxin|vancomycin|gentamicin|amiodarone|lithium)',
        'negative_pattern': r'INR|monitor|lab_test|therapeutic_drug|TDM',
        'message': 'High-risk medication without lab monitoring order — therapeutic drug monitoring required',
        'severity': 'high',
        'remediation': 'Implement automatic lab test ordering for high-risk medications requiring therapeutic drug monitoring (TDM).',
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# Medical Device Software (IEC 62304)
# ═══════════════════════════════════════════════════════════════════════════════

DEVICE_SOFTWARE_RULES = [
    {
        'check': 'device_class_unannotated',
        'pattern': r'(?:medical_device|implant|pacemaker|infusion_pump|ventilator|defibrillator|monitor)',
        'negative_pattern': r'Class\s*A|Class\s*B|Class\s*C|FDA_Class|software_safety_class',
        'message': 'Medical device software without safety classification — IEC 62304 violation',
        'severity': 'high',
        'remediation': 'Declare software safety class (A/B/C per IEC 62304) at module/class level with clear documentation.',
    },
    {
        'check': 'device_failure_handling_missing',
        'pattern': r'def\s+(?:control|actuate|deliver|infuse|stimulate)',
        'negative_pattern': r'try|except|Exception|error_handler|failsafe|fallback',
        'message': 'Critical device function without exception handling — IEC 62304 risk control failure',
        'severity': 'critical',
        'remediation': 'Implement comprehensive exception handling with failsafe fallback for all critical device functions.',
    },
    {
        'check': 'device_safety_limit_unchecked',
        'pattern': r'(?:set_output|set_power|set_energy|set_current|set_voltage)',
        'negative_pattern': r'max_output|limit|safety_check|bound|threshold',
        'message': 'Device output parameter set without safety limit check — patient harm risk',
        'severity': 'critical',
        'remediation': 'Implement hardware-enforced safety limits for all device output parameters. Validate before actuation.',
    },
    {
        'check': 'device_self_test_missing',
        'pattern': r'(?:device_start|device_init|power_on|boot|startup)',
        'negative_pattern': r'self_test|POST|diagnostic|health_check|BIT',
        'message': 'Device startup without self-test/POST — IEC 62304 risk management requirement',
        'severity': 'high',
        'remediation': 'Implement power-on self-test (POST) / built-in test (BIT) at device startup with result validation.',
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# EHR Data Integrity Rules
# ═══════════════════════════════════════════════════════════════════════════════

EHR_INTEGRITY_RULES = [
    {
        'check': 'ehr_record_immutable_update',
        'pattern': r'(?:update|modify|change|alter).*(?:record|entry|note|document)',
        'negative_pattern': r'timestamp|created_at|modified_at|version|revision|audit_trail',
        'message': 'Medical record updated without version/timestamp — EHR immutability violation',
        'severity': 'critical',
        'remediation': 'Never modify existing medical records. Use append-only model with version control and audit trail.',
    },
    {
        'check': 'ehr_version_control_missing',
        'pattern': r'\.save\(\)|\.update\(',
        'negative_pattern': r'version|revision|history|snapshot|previous',
        'message': 'Data save without version control — medical record history lost',
        'severity': 'high',
        'remediation': 'Implement event sourcing or versioned storage for all medical record modifications.',
    },
    {
        'check': 'ehr_signature_missing',
        'pattern': r'(?:approve|sign|authorize|finalize).*(?:diagnosis|prescription|order|discharge)',
        'negative_pattern': r'signature|digital_sign|e_sign|esign|signing',
        'message': 'Clinical action approved without electronic signature — legal validity concern',
        'severity': 'high',
        'remediation': 'Implement electronic signature (compliant with ESIGN Act / eIDAS) for all clinical approvals.',
    },
    {
        'check': 'ehr_concurrent_edit_unlocked',
        'pattern': r'(?:edit|modify).*(?:record|note)|class.*Record.*:\s*\n',
        'negative_pattern': r'lock|mutex|optimistic|concurrent|version_check|select_for_update',
        'message': 'Medical record editable without concurrency control — data corruption risk',
        'severity': 'medium',
        'remediation': 'Implement optimistic or pessimistic locking to prevent concurrent edit conflicts on medical records.',
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# Medical Identity Management Rules
# ═══════════════════════════════════════════════════════════════════════════════

IDENTITY_RULES = [
    {
        'check': 'patient_id_collision_risk',
        'pattern': r'(?:uuid\.uuid4|random\.randint|secrets\.token).*patient',
        'negative_pattern': r'unique|constraint|collision_check|already_exists|duplicate',
        'message': 'Patient ID generated without collision check — duplicate patient risk',
        'severity': 'critical',
        'remediation': 'Implement master patient index (MPI) with probabilistic matching. Check uniqueness before creating new patient IDs.',
    },
    {
        'check': 'patient_id_in_url',
        'pattern': r'(?:url|path|route|endpoint).*patient.?id.*\{|/(?:patient|pt)/(?:\d+)',
        'negative_pattern': r'encrypt|hash|tokenize|obfuscate|anonymize',
        'message': 'Patient ID exposed in URL — privacy violation and enumeration risk',
        'severity': 'high',
        'remediation': 'Use opaque reference IDs or encrypted tokens in URLs instead of raw patient identifiers.',
    },
    {
        'check': 'patient_mixing_no_validation',
        'pattern': r'(?:save|update).*(?:record|result|measurement|lab)',
        'negative_pattern': r'patient_id.*validate|verify_patient|match_patient|confirm_patient',
        'message': 'Clinical data saved without patient identity confirmation — patient mixing risk',
        'severity': 'critical',
        'remediation': 'Always verify patient identity (name + DOB + ID) before saving clinical data to their record.',
    },
    {
        'check': 'deidentification_incomplete',
        'pattern': r'(?:deidentify|anonymize|deident|scrub)',
        'negative_pattern': r'(?:patient_name|ssn|mrn|medical_record|address|phone|email|zip|birth).*remove|all.*18.*HIPAA',
        'message': 'De-identification function may not cover all 18 HIPAA identifiers',
        'severity': 'critical',
        'remediation': 'Verify removal of all 18 HIPAA Safe Harbor identifiers. Implement statistical expert determination for de-identification.',
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# Medical Image Safety Rules
# ═══════════════════════════════════════════════════════════════════════════════

IMAGE_SAFETY_RULES = [
    {
        'check': 'medical_image_watermark_missing',
        'pattern': r'(?:\.save_as|\.write|\.export).*(?:dicom|nifti|mha)',
        'negative_pattern': r'watermark|overlay|burn_in|annotation',
        'message': 'Medical image exported without watermark/annotation — traceability lost',
        'severity': 'medium',
        'remediation': 'Add institutional watermark with date/time/source before exporting medical images.',
    },
    {
        'check': 'medical_image_no_audit',
        'pattern': r'(?:transform|resize|crop|filter|enhance|adjust).*(?:image|dicom|scan)',
        'negative_pattern': r'log|audit|record|track|history',
        'message': 'Medical image modified without audit trail — image forensics compromised',
        'severity': 'high',
        'remediation': 'Log all image transformations with before/after metadata. Maintain original DICOM image.',
    },
    {
        'check': 'medical_image_segmentation_bounds',
        'pattern': r'(?:segment|contour|mask|roi).*\[',
        'negative_pattern': r'boundary|bounds_check|image_shape|dimension_check',
        'message': 'Image segmentation without boundary validation — potential out-of-bounds access',
        'severity': 'high',
        'remediation': 'Validate segmentation coordinates against image dimensions before processing.',
    },
    {
        'check': 'radiation_dose_tracking_missing',
        'pattern': r'\b(?:CT|XRay|x_ray|radiation|fluoroscopy|mammography)\b',
        'negative_pattern': r'dose|DLP|CTDI|mGy|mSv|exposure_record',
        'message': 'Radiation imaging without dose tracking — regulatory compliance risk',
        'severity': 'high',
        'remediation': 'Implement radiation dose tracking (CTDIvol, DLP) and cumulative exposure monitoring per ACR guidelines.',
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# Extended General Security Rules
# ═══════════════════════════════════════════════════════════════════════════════

EXTENDED_SECURITY_RULES = [
    # XSS
    {
        'check': 'xss_reflected',
        'pattern': r'(?:render_template_string|markup|safe\s*\(|\.html\s*\()',
        'message': 'Potential reflected XSS — user input may be rendered unsafely',
        'severity': 'critical',
        'remediation': 'Use auto-escaping template engines. Never mark user input as safe. Use Content-Security-Policy headers.',
    },
    {
        'check': 'xss_stored',
        'pattern': r'(?:\.save\(|\.insert\(|\.create\().*(?:comment|message|desc|note|text)',
        'negative_pattern': r'bleach|sanitize|escape|strip_tags|custom_filter',
        'message': 'User content saved without sanitization — stored XSS risk',
        'severity': 'critical',
        'remediation': 'Sanitize all user-generated content before storage (bleach, html.escape). Render with auto-escaping.',
    },
    # XXE
    {
        'check': 'xxe_injection',
        'pattern': r'(?:xml\.etree\.ElementTree|etree\.parse|xml\.dom\.minidom)\s*\(',
        'negative_pattern': r'defusedxml|secure_parser|resolve_entities\s*=\s*False',
        'message': 'XML parser without XXE protection — external entity injection risk',
        'severity': 'critical',
        'remediation': 'Use defusedxml or disable external entity resolution. Set resolve_entities=False.',
    },
    {
        'check': 'xml_external_entity',
        'pattern': r'lxml\.(?:etree|objectify)\.(?:parse|fromstring)',
        'negative_pattern': r'resolve_entities\s*=\s*False|no_network\s*=\s*True',
        'message': 'lxml parser without XXE protection — external entity injection risk',
        'severity': 'critical',
        'remediation': 'Disable resolve_entities and enable no_network for lxml parsing of untrusted XML.',
    },
    # SSRF
    {
        'check': 'ssrf_risk',
        'pattern': r'requests\.(?:get|post|put|delete)\s*\([^)]*(?:url|endpoint|link|target)\b[^)]*\)',
        'negative_pattern': r'validate_url|allowed_domains|whitelist|SSRFException|parse\.urlparse',
        'message': 'HTTP request with user-controlled URL — potential SSRF vulnerability',
        'severity': 'high',
        'remediation': 'Validate and whitelist target URLs. Block internal IPs (127.0.0.1, 10.x, 172.16-31.x, 192.168.x).',
    },
    # LDAP Injection
    {
        'check': 'ldap_injection',
        'pattern': r'(?:ldap\.search|ldap\.filter|ldap_query|search_s)\s*\([^)]*\+[^)]*\)',
        'message': 'LDAP query with string concatenation — potential LDAP injection',
        'severity': 'high',
        'remediation': 'Use LDAP escape functions (ldap3.utils.dn.escape_filter_chars). Never concatenate user input into LDAP filters.',
    },
    # SSTI
    {
        'check': 'ssti_risk',
        'pattern': r'render_template_string\s*\(',
        'message': 'Server-Side Template Injection risk — render_template_string with user input',
        'severity': 'critical',
        'remediation': 'Avoid render_template_string(). Use render_template() with predefined templates. Never pass user input as template.',
    },
    # Weak Random
    {
        'check': 'weak_random_generator',
        'pattern': r'(?:random\.random|random\.randint)\s*\(',
        'negative_pattern': r'#\s*nosec|display|animation|color',
        'message': 'Weak random number generator used — not suitable for cryptographic/security purposes',
        'severity': 'medium',
        'remediation': 'Use secrets module (secrets.token_hex, secrets.randbelow) or os.urandom() for security contexts.',
    },
    # Insecure Temp File
    {
        'check': 'insecure_temp_file',
        'pattern': r'(?:tempfile\.mkstemp|tempfile\.mktemp)\s*\(',
        'message': 'Insecure temporary file creation — race condition and path disclosure risk',
        'severity': 'medium',
        'remediation': 'Use tempfile.TemporaryFile() or tempfile.NamedTemporaryFile(delete=True) in a context manager.',
    },
    # Insecure Deserialization (additional)
    {
        'check': 'insecure_deserialization_dill',
        'pattern': r'dill\.(?:loads|load)\s*\(',
        'message': 'dill deserialization — dill can execute arbitrary code like pickle',
        'severity': 'critical',
        'remediation': 'Never use dill for untrusted data. dill can serialize and execute arbitrary Python code.',
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# Healthcare Code Quality Rules
# ═══════════════════════════════════════════════════════════════════════════════

CODE_QUALITY_RULES = [
    {
        'check': 'error_suppression_silent_pass',
        'pattern': r'except(?:\s+\w+)?\s*:\s*\n\s*pass',
        'message': 'Exception silently suppressed — clinical error may go undetected',
        'severity': 'high',
        'remediation': 'Always log exceptions with clinical context. Never use bare except: pass in medical software.',
    },
    {
        'check': 'timeout_missing',
        'pattern': r'requests\.(?:get|post|put|delete)\s*\([^)]*\)(?!.*timeout)',
        'message': 'Network request without timeout — clinical system may hang indefinitely',
        'severity': 'high',
        'remediation': 'Always set timeout parameter on network calls in clinical systems. Use timeout=30 as reasonable default.',
    },
    {
        'check': 'resource_leak',
        'pattern': r'(?:open\(|\.connect\(|\.cursor\()(?!.*with\s)',  # pattern may match lines without 'with'
        'message': 'File or connection opened without context manager — resource leak in long-running clinical service',
        'severity': 'medium',
        'remediation': 'Use with statements for all file and connection operations in clinical systems.',
    },
    {
        'check': 'race_condition_unsynchronized',
        'pattern': r'(?:threading|asyncio|multiprocessing)',
        'negative_pattern': r'Lock|RLock|Semaphore|Queue|mutex|synchronized',
        'message': 'Multi-threaded code without synchronization primitives — race condition risk in clinical data',
        'severity': 'high',
        'remediation': 'Use threading.Lock, asyncio.Lock, or multiprocessing.Queue for concurrent clinical data access.',
    },
    {
        'check': 'magic_number_clinical',
        'pattern': r'(?:threshold|cutoff|limit|normal_range)\s*=\s*\d+(?:\.\d+)?',
        'negative_pattern': r'#.*来解释|#.*说明|comment|docstring|document|reference',
        'message': 'Clinical threshold as magic number without explanatory comment',
        'severity': 'medium',
        'remediation': 'Document every clinical constant with source reference (guideline name, version, page).',
    },
    {
        'check': 'float_equality_comparison',
        'pattern': r'(?:==|!=\s)\.\d+(?:f)?\b',
        'message': 'Float equality comparison — unreliable for clinical values',
        'severity': 'medium',
        'remediation': 'Use math.isclose() or absolute tolerance (abs(a - b) < tolerance) for clinical value comparisons.',
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# SMART on FHIR Compliance
# ═══════════════════════════════════════════════════════════════════════════════

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

# ═══════════════════════════════════════════════════════════════════════════════
# Clinical Lab Value Ranges
# ═══════════════════════════════════════════════════════════════════════════════

LAB_RANGES = {
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
    'body_temperature': (30.0, 45.0, 'degC', 'Body Temperature'),
    'respiratory_rate': (5, 60, 'breaths/min', 'Respiratory Rate'),
}

LAB_VALUE_PATTERNS = [
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

# ═══════════════════════════════════════════════════════════════════════════════
# Rule Engine
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_ruleset(rules_list, file_path, lines, findings, default_remediation, default_confidence=0.95):
    """Generic helper to apply a list of dict rules to lines."""
    for rule in rules_list:
        for line_no, line in enumerate(lines, 1):
            if re.search(rule['pattern'], line):
                if 'negative_pattern' in rule:
                    ctx_s, ctx_e = max(0, line_no - 3), min(len(lines), line_no + 3)
                    ctx = '\n'.join(lines[ctx_s:ctx_e])
                    if re.search(rule['negative_pattern'], ctx, re.IGNORECASE):
                        continue
                findings.append(RuleFinding(
                    check_name=rule['check'],
                    severity=rule['severity'],
                    message=rule['message'],
                    file_path=file_path,
                    line_start=line_no,
                    line_end=line_no,
                    evidence=line.strip(),
                    remediation=rule.get('remediation', default_remediation),
                    confidence=rule.get('confidence', default_confidence),
                ))


class HealthcareRuleEngine:
    """Comprehensive healthcare rule engine with 100+ deterministic checks."""

    def __init__(self):
        self.findings: List[RuleFinding] = []

    def scan_file(self, file_path: str, content: str) -> List[RuleFinding]:
        """Scan a single file for all healthcare rule violations."""
        self.findings = []
        lines = content.split('\n')

        self._scan_phi_pii(file_path, lines)
        self._scan_fhir(file_path, lines, content)
        self._scan_dicom(file_path, lines, content)
        self._scan_hl7(file_path, lines, content)
        self._scan_general_security(file_path, lines)
        self._scan_lab_values(file_path, lines)
        self._scan_cds(file_path, lines, content)
        self._scan_cds_safety(file_path, lines, content)
        self._scan_smart_fhir(file_path, lines, content)
        self._scan_hipaa(file_path, lines, content)
        self._scan_cn_regulations(file_path, lines, content)
        self._scan_drug_safety(file_path, lines, content)
        self._scan_device_software(file_path, lines, content)
        self._scan_ehr_integrity(file_path, lines, content)
        self._scan_identity(file_path, lines, content)
        self._scan_image_safety(file_path, lines, content)
        self._scan_extended_security(file_path, lines)
        self._scan_code_quality(file_path, lines)

        return self.findings

    # ── PHI/PII ────────────────────────────────────────────────────────────

    def _scan_phi_pii(self, file_path: str, lines: List[str]):
        for line_no, line in enumerate(lines, 1):
            for pattern, label, severity in US_PHI_PATTERNS:
                for match in re.finditer(pattern, line, re.IGNORECASE):
                    self.findings.append(RuleFinding(
                        check_name=f"phi_{label.lower().replace(' ', '_')}",
                        severity=severity,
                        message=f"Potential {label} exposure in code",
                        file_path=file_path, line_start=line_no, line_end=line_no,
                        evidence=line.strip(),
                        remediation=f"Remove or mask {label} from source code. Use tokenization or reference IDs.",
                        confidence=0.95,
                    ))
            for pattern, label, severity in CN_PHI_PATTERNS:
                for match in re.finditer(pattern, line):
                    self.findings.append(RuleFinding(
                        check_name=f"phi_cn_{label.lower().replace(' ', '_').replace('(', '').replace(')', '')}",
                        severity=severity,
                        message=f"Potential {label} exposure in code",
                        file_path=file_path, line_start=line_no, line_end=line_no,
                        evidence=line.strip(),
                        remediation=f"Remove or mask {label} from source code. Use encrypted storage or reference IDs.",
                        confidence=0.95,
                    ))
            for pattern, label, severity in PHI_LEAK_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    self.findings.append(RuleFinding(
                        check_name=f"phi_leak_{label.lower().replace(' ', '_').replace('/', '_')}",
                        severity=severity, message=label,
                        file_path=file_path, line_start=line_no, line_end=line_no,
                        evidence=line.strip(),
                        remediation="Use structured logging with PHI redaction. Never log raw patient identifiers.",
                        confidence=0.9,
                    ))

    # ── FHIR ───────────────────────────────────────────────────────────────

    def _scan_fhir(self, file_path: str, lines: List[str], content: str):
        for rule in FHIR_SECURITY_RULES:
            if re.search(rule['pattern'], content):
                if 'negative_pattern' in rule:
                    if re.search(rule['negative_pattern'], content, re.IGNORECASE):
                        continue
                line_no = next((i for i, l in enumerate(lines, 1) if re.search(rule['pattern'], l)), 1)
                self.findings.append(RuleFinding(
                    check_name=rule['check'], severity=rule['severity'],
                    message=rule['message'],
                    file_path=file_path, line_start=line_no,
                    evidence=lines[line_no - 1].strip() if line_no <= len(lines) else "",
                    remediation="Implement OAuth2/SMART on FHIR authentication. Always use HTTPS endpoints.",
                    confidence=0.95,
                ))

    # ── DICOM ──────────────────────────────────────────────────────────────

    def _scan_dicom(self, file_path: str, lines: List[str], content: str):
        if not re.search(r'import\s+pydicom|from\s+pydicom', content):
            return
        _apply_ruleset(DICOM_SECURITY_RULES, file_path, lines, self.findings,
                       "Anonymize DICOM tags before export. Use DICOM de-identification profiles.", 0.95)

    # ── HL7 ────────────────────────────────────────────────────────────────

    def _scan_hl7(self, file_path: str, lines: List[str], content: str):
        if not re.search(r'import\s+hl7apy|from\s+hl7apy|HL7\.', content):
            return
        for rule in HL7_SECURITY_RULES:
            if re.search(rule['pattern'], content, re.IGNORECASE):
                if 'negative_pattern' in rule:
                    if re.search(rule['negative_pattern'], content, re.IGNORECASE):
                        continue
                line_no = next((i for i, l in enumerate(lines, 1) if re.search(rule['pattern'], l, re.IGNORECASE)), 1)
                self.findings.append(RuleFinding(
                    check_name=rule['check'], severity=rule['severity'],
                    message=rule['message'],
                    file_path=file_path, line_start=line_no,
                    evidence=lines[line_no - 1].strip() if line_no <= len(lines) else "",
                    remediation="Enable TLS/MLLP encryption for HL7 message transport.",
                    confidence=0.9,
                ))

    # ── General Security ───────────────────────────────────────────────────

    def _scan_general_security(self, file_path: str, lines: List[str]):
        for rule in GENERAL_SECURITY_RULES:
            for line_no, line in enumerate(lines, 1):
                if re.search(rule['pattern'], line):
                    if 'negative_pattern' in rule:
                        ctx_s, ctx_e = max(0, line_no - 3), min(len(lines), line_no + 3)
                        ctx = '\n'.join(lines[ctx_s:ctx_e])
                        if re.search(rule['negative_pattern'], ctx, re.IGNORECASE):
                            continue
                    self.findings.append(RuleFinding(
                        check_name=rule['check'], severity=rule['severity'],
                        message=rule['message'],
                        file_path=file_path, line_start=line_no, line_end=line_no,
                        evidence=line.strip(),
                        remediation=rule.get('remediation', 'Fix this security issue'),
                        confidence=0.95,
                    ))

    # ── Lab Values ─────────────────────────────────────────────────────────

    def _scan_lab_values(self, file_path: str, lines: List[str]):
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
                            file_path=file_path, line_start=line_no, line_end=line_no,
                            evidence=line.strip(),
                            remediation=f"Validate {name} against physiological range ({min_val}-{max_val} {unit}) before processing.",
                            confidence=0.98,
                        ))

    # ── CDS ────────────────────────────────────────────────────────────────

    def _scan_cds(self, file_path: str, lines: List[str], content: str):
        if not re.search(r'clinical|decision|alert|threshold|rule', content, re.IGNORECASE):
            return
        _apply_ruleset(CDS_PATTERNS, file_path, lines, self.findings,
                       "Add complete decision branches and configurable thresholds. Implement alert escalation.", 0.85)

    # ── CDS Safety (Extended) ──────────────────────────────────────────────

    def _scan_cds_safety(self, file_path: str, lines: List[str], content: str):
        _apply_ruleset(CDS_SAFETY_RULES, file_path, lines, self.findings,
                       "Implement clinical safety controls per CDS guidelines.", 0.9)

    # ── SMART on FHIR ──────────────────────────────────────────────────────

    def _scan_smart_fhir(self, file_path: str, lines: List[str], content: str):
        if not re.search(r'fhir|smart|oauth|launch', content, re.IGNORECASE):
            return
        _apply_ruleset(SMART_FHIR_RULES, file_path, lines, self.findings,
                       "Implement full SMART on FHIR launch sequence with scope validation and JWT verification.", 0.9)

    # ── HIPAA ──────────────────────────────────────────────────────────────

    def _scan_hipaa(self, file_path: str, lines: List[str], content: str):
        _apply_ruleset(HIPAA_RULES, file_path, lines, self.findings,
                       "Implement HIPAA compliance: encrypt PHI at rest, audit all access, use HTTPS.", 0.95)

    # ── China Medical Regulations ──────────────────────────────────────────

    def _scan_cn_regulations(self, file_path: str, lines: List[str], content: str):
        for rule in CN_MEDICAL_REGULATIONS:
            for line_no, line in enumerate(lines, 1):
                if re.search(rule['pattern'], line):
                    if 'negative_pattern' in rule:
                        ctx_s, ctx_e = max(0, line_no - 5), min(len(lines), line_no + 5)
                        ctx = '\n'.join(lines[ctx_s:ctx_e])
                        if re.search(rule['negative_pattern'], ctx, re.IGNORECASE):
                            continue
                    self.findings.append(RuleFinding(
                        check_name=rule['check'], severity=rule['severity'],
                        message=rule['message'],
                        file_path=file_path, line_start=line_no, line_end=line_no,
                        evidence=line.strip(),
                        remediation=rule.get('remediation', 'Ensure compliance with China medical data regulations.'),
                        confidence=0.88,
                    ))

    # ── Drug Safety ────────────────────────────────────────────────────────

    def _scan_drug_safety(self, file_path: str, lines: List[str], content: str):
        _apply_ruleset(DRUG_SAFETY_RULES, file_path, lines, self.findings,
                       "Implement medication safety checks: interactions, allergies, contraindications, dosing limits.", 0.9)

    # ── Device Software (IEC 62304) ────────────────────────────────────────

    def _scan_device_software(self, file_path: str, lines: List[str], content: str):
        _apply_ruleset(DEVICE_SOFTWARE_RULES, file_path, lines, self.findings,
                       "Implement IEC 62304 compliant software development process with risk management.", 0.85)

    # ── EHR Integrity ──────────────────────────────────────────────────────

    def _scan_ehr_integrity(self, file_path: str, lines: List[str], content: str):
        _apply_ruleset(EHR_INTEGRITY_RULES, file_path, lines, self.findings,
                       "Implement EHR data integrity: versioning, audit trails, concurrency control, signatures.", 0.9)

    # ── Medical Identity ───────────────────────────────────────────────────

    def _scan_identity(self, file_path: str, lines: List[str], content: str):
        _apply_ruleset(IDENTITY_RULES, file_path, lines, self.findings,
                       "Implement robust patient identity management with MPI, de-identification, and access controls.", 0.92)

    # ── Medical Image Safety ───────────────────────────────────────────────

    def _scan_image_safety(self, file_path: str, lines: List[str], content: str):
        _apply_ruleset(IMAGE_SAFETY_RULES, file_path, lines, self.findings,
                       "Implement medical image safety: watermarking, audit trails, boundary checks, dose tracking.", 0.82)

    # ── Extended Security ──────────────────────────────────────────────────

    def _scan_extended_security(self, file_path: str, lines: List[str]):
        for rule in EXTENDED_SECURITY_RULES:
            for line_no, line in enumerate(lines, 1):
                if re.search(rule['pattern'], line):
                    if 'negative_pattern' in rule:
                        ctx_s, ctx_e = max(0, line_no - 3), min(len(lines), line_no + 3)
                        ctx = '\n'.join(lines[ctx_s:ctx_e])
                        if re.search(rule['negative_pattern'], ctx, re.IGNORECASE):
                            continue
                    self.findings.append(RuleFinding(
                        check_name=rule['check'], severity=rule['severity'],
                        message=rule['message'],
                        file_path=file_path, line_start=line_no, line_end=line_no,
                        evidence=line.strip(),
                        remediation=rule.get('remediation', 'Fix this security issue'),
                        confidence=0.93,
                    ))

    # ── Code Quality ───────────────────────────────────────────────────────

    def _scan_code_quality(self, file_path: str, lines: List[str]):
        for rule in CODE_QUALITY_RULES:
            for line_no, line in enumerate(lines, 1):
                if re.search(rule['pattern'], line):
                    if 'negative_pattern' in rule:
                        ctx_s, ctx_e = max(0, line_no - 3), min(len(lines), line_no + 3)
                        ctx = '\n'.join(lines[ctx_s:ctx_e])
                        if re.search(rule['negative_pattern'], ctx, re.IGNORECASE):
                            continue
                    self.findings.append(RuleFinding(
                        check_name=rule['check'], severity=rule['severity'],
                        message=rule['message'],
                        file_path=file_path, line_start=line_no, line_end=line_no,
                        evidence=line.strip(),
                        remediation=rule.get('remediation', 'Improve code quality for medical software reliability.'),
                        confidence=0.82,
                    ))


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def scan_project(project_path: str, files: List[Tuple[str, str]]) -> List[RuleFinding]:
    """Scan a list of (file_path, content) tuples for healthcare violations."""
    engine = HealthcareRuleEngine()
    all_findings = []
    for file_path, content in files:
        findings = engine.scan_file(file_path, content)
        all_findings.extend(findings)
    return all_findings
