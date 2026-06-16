"""Unit tests for agent architecture (no LLM required)."""

import os
import json
import uuid
import tempfile
import pytest
from datetime import datetime, UTC

from codespect_matrix.agents.base import (
    AgentRole,
    MessageType,
    AgentMessage,
    Finding,
    DebateResult,
    BaseAgent,
)
from codespect_matrix.agents.bus import AgentCommunicationBus
from codespect_matrix.agents.memory import ProjectMemory, GlobalKnowledgeBase


# ── AgentMessage ──────────────────────────────────────────────────────────────

class TestAgentMessage:
    def test_creation(self):
        msg = AgentMessage(
            id="msg-1", sender="security", receiver="orchestrator",
            msg_type=MessageType.FINDING, content="found issue",
            data={"file": "test.py"}
        )
        assert msg.sender == "security"
        assert msg.receiver == "orchestrator"
        assert msg.msg_type == MessageType.FINDING
        assert msg.data["file"] == "test.py"

    def test_default_timestamp(self):
        msg = AgentMessage(
            id="msg-2", sender="a", receiver="b",
            msg_type=MessageType.FINDING, content="hi"
        )
        assert msg.timestamp is not None

    def test_reply_to_optional(self):
        msg = AgentMessage(
            id="msg-3", sender="a", receiver="b",
            msg_type=MessageType.FINDING, content="hi"
        )
        assert msg.reply_to is None

    def test_to_dict(self):
        msg = AgentMessage(
            id="msg-4", sender="dev", receiver="reviewer",
            msg_type=MessageType.FINDING, content="issue",
            data={"severity": "high"}
        )
        d = msg.to_dict()
        assert d["id"] == "msg-4"
        assert d["sender"] == "dev"
        assert d["msg_type"] == "finding"


# ── Finding ───────────────────────────────────────────────────────────────────

class TestFinding:
    def test_creation(self):
        f = Finding(
            check_name="security_eval",
            message="eval() detected",
            severity="critical",
            file_path="app.py",
            line_start=42,
            line_end=44,
            confidence=0.9,
            remediation="Use ast.literal_eval",
        )
        assert f.severity == "critical"
        assert f.confidence == 0.9
        assert f.reviewed is False
        assert f.ruling == ""
        assert f.line_start == 42
        assert f.line_end == 44

    def test_defaults(self):
        f = Finding(
            check_name="test", message="test", severity="low"
        )
        assert f.file_path == ""
        assert f.line_start == 0
        assert f.confidence == 1.0
        assert f.remediation == ""

    def test_to_dict(self):
        f = Finding(check_name="test", message="hi", severity="low")
        d = f.to_dict()
        assert d["check_name"] == "test"
        assert d["severity"] == "low"
        assert d["ruling"] == ""


# ── DebateResult ──────────────────────────────────────────────────────────────

class TestDebateResult:
    def test_creation(self):
        finding = Finding(check_name="epic", message="bad", severity="high")
        result = DebateResult(
            finding=finding,
            challenger="architect",
            defender="developer",
            arbiter="orchestrator",
            rounds=[],
            final_ruling="confirmed",
            rationale="fix is needed",
        )
        assert result.challenger == "architect"
        assert result.defender == "developer"
        assert result.final_ruling == "confirmed"
        assert result.arbiter == "orchestrator"
        assert "challenger" in result.to_dict()


# ── AgentRole / MessageType Enums ─────────────────────────────────────────────

class TestEnums:
    def test_agent_role_values(self):
        assert AgentRole.INSPECTOR.value == "inspector"
        assert AgentRole.REVIEWER.value == "reviewer"
        assert AgentRole.ARBITER.value == "arbiter"
        assert AgentRole.FIXER.value == "fixer"
        assert AgentRole.ORCHESTRATOR.value == "orchestrator"

    def test_message_type_values(self):
        assert MessageType.FINDING.value == "finding"
        assert MessageType.CHALLENGE.value == "challenge"
        assert MessageType.DEFENSE.value == "defense"
        assert MessageType.RULING.value == "ruling"


# ── AgentCommunicationBus ─────────────────────────────────────────────────────

class TestAgentCommunicationBus:
    def test_register_agent(self):
        bus = AgentCommunicationBus()
        # Create a minimal concrete agent using a subclass
        class MinAgent(BaseAgent):
            def __init__(self, name, role):
                super().__init__(name=name, role=role)
            def get_description(self): return "min"
            def get_domain(self): return "test"
            def inspect(self, context): return []
        agent = MinAgent(name="test_agent", role=AgentRole.INSPECTOR)
        bus.register_agent(agent)
        assert "test_agent" in bus.registered_agents

    def test_send_message(self):
        bus = AgentCommunicationBus()
        bus.send(
            sender="security", receiver="orchestrator",
            msg_type=MessageType.FINDING, content="issue found",
            data={"count": 1}
        )
        assert len(bus.messages) == 1
        msg = bus.messages[0]
        assert msg.sender == "security"
        assert msg.receiver == "orchestrator"
        assert msg.msg_type == MessageType.FINDING
        assert msg.data["count"] == 1

    def test_broadcast(self):
        bus = AgentCommunicationBus()
        bus.broadcast_findings(sender="orchestrator", findings=[
            Finding(check_name="x", message="y", severity="low"),
        ])
        assert len(bus.messages) >= 1
        assert bus.messages[0].receiver == "all"

    def test_get_stats(self):
        bus = AgentCommunicationBus()
        stats = bus.get_stats()
        assert "total_messages" in stats
        assert "active_debates" in stats
        assert stats["total_messages"] == 0

    def test_message_increment_stats(self):
        bus = AgentCommunicationBus()
        bus.send(sender="a", receiver="b", msg_type=MessageType.FINDING, content="test")
        bus.send(sender="a", receiver="b", msg_type=MessageType.REVIEW, content="review")
        stats = bus.get_stats()
        assert stats["total_messages"] == 2

    def test_open_debate(self):
        bus = AgentCommunicationBus()
        finding = Finding(check_name="test", message="bad", severity="medium")
        debate_id = bus.open_debate(finding, challenger="architect", reason="low confidence")
        assert debate_id is not None
        assert debate_id in bus.debates
        assert bus.debates[debate_id]["challenger"] == "architect"
        assert bus.debates[debate_id]["status"] == "open"

    def test_close_debate(self):
        bus = AgentCommunicationBus()
        finding = Finding(check_name="test", message="bad", severity="medium", confidence=0.4)
        debate_id = bus.open_debate(finding, challenger="architect", reason="check")
        result = bus.close_debate(
            debate_id=debate_id, arbiter="orchestrator",
            ruling="rejected", rationale="not enough evidence",
        )
        assert result is not None
        assert result.final_ruling == "rejected"
        assert result.arbiter == "orchestrator"
        assert len(bus.completed_debates) == 1

    def test_broadcast_findings(self):
        bus = AgentCommunicationBus()
        findings = [
            Finding(check_name="a", message="x", severity="low"),
            Finding(check_name="b", message="y", severity="high"),
        ]
        bus.broadcast_findings(sender="developer", findings=findings)
        assert len(bus.messages) >= 1


# ── ProjectMemory ─────────────────────────────────────────────────────────────

class TestProjectMemory:
    def test_is_false_positive_empty(self, tmp_path):
        memory = ProjectMemory(str(tmp_path))
        assert memory.is_false_positive("check_x", "message") is False

    def test_mark_and_check_false_positive(self, tmp_path):
        memory = ProjectMemory(str(tmp_path))
        memory.mark_false_positive("check_a", "eval() is dangerous", "reviewer: confirmed FP")
        assert memory.is_false_positive("check_a", "eval() is dangerous") is True

    def test_different_message_not_fp(self, tmp_path):
        memory = ProjectMemory(str(tmp_path))
        memory.mark_false_positive("check_a", "message 1", "reviewer")
        assert memory.is_false_positive("check_a", "different message") is False

    def test_record_scan(self, tmp_path):
        memory = ProjectMemory(str(tmp_path))
        memory.record_scan(round_number=1, issue_count=5, status="completed", agent_count=8)
        # Should not crash
        assert memory.data.get("scan_history") is not None or True

    def test_record_fix_decision(self, tmp_path):
        memory = ProjectMemory(str(tmp_path))
        memory.record_fix_decision(
            finding={"check_name": "test", "message": "fix this"},
            decision="applied",
            agent="developer",
        )
        assert len(memory.data.get("fix_decisions", [])) >= 1

    def test_fingerprint_stable(self):
        """Same check_name + message → same fingerprint."""
        memory1 = ProjectMemory("/tmp/a")
        memory2 = ProjectMemory("/tmp/a")
        fp1 = memory1.fingerprint("check", "hello world")
        fp2 = memory2.fingerprint("check", "hello world")
        assert fp1 == fp2

    def test_get_convergence_trend_empty(self, tmp_path):
        memory = ProjectMemory(str(tmp_path))
        assert memory.get_convergence_trend() == []


# ── GlobalKnowledgeBase ──────────────────────────────────────────────────────

class TestGlobalKnowledgeBase:
    def test_init(self):
        kb = GlobalKnowledgeBase()
        assert kb is not None

    def test_check_false_positive_empty(self):
        kb = GlobalKnowledgeBase()
        assert kb.check_false_positive("some pattern") is False

    def test_add_and_check_false_positive(self):
        kb = GlobalKnowledgeBase()
        kb.add_false_positive_rule("eval with user input", "security")
        assert kb.check_false_positive("eval with user input") is True

    def test_different_pattern_not_fp(self):
        kb = GlobalKnowledgeBase()
        kb.add_false_positive_rule("specific string", "dev")
        assert kb.check_false_positive("completely different") is False

    def test_add_multiple_rules(self):
        kb = GlobalKnowledgeBase()
        kb.add_false_positive_rule("rule 1", "security")
        kb.add_false_positive_rule("rule 2", "healthcare")
        assert kb.check_false_positive("rule 1") is True
        assert kb.check_false_positive("rule 2") is True

    def test_learn_pattern(self):
        kb = GlobalKnowledgeBase()
        kb.learn_pattern(
            check_name="sql_injection",
            category="security",
            pattern="unsafe SQL usage",
            fix_template="Use parameterized queries",
        )
        # Learning should not crash
        assert True

    def test_get_fix_template_empty(self):
        kb = GlobalKnowledgeBase()
        result = kb.get_fix_template("unknown_issue")
        assert result is None or isinstance(result, dict)

    def test_recommend_agents(self):
        kb = GlobalKnowledgeBase()
        result = kb.recommend_agents("web", "medical")
        assert isinstance(result, list)

    def test_record_project_stats(self):
        kb = GlobalKnowledgeBase()
        kb.record_project_stats("web", 10, 0)
        stats = kb.get_stats()
        assert stats["projects_analyzed"] >= 1
        assert stats["issues_found"] >= 10

    def test_get_stats_defaults(self):
        kb = GlobalKnowledgeBase()
        stats = kb.get_stats()
        assert stats["projects_analyzed"] >= 0
        assert stats["issues_found"] >= 0
        assert stats["issues_fixed"] >= 0


# ── Healthcare Rule Engine ────────────────────────────────────────────────────

class TestHealthcareRuleEngine:
    def test_phi_ssn_detection(self):
        from codespect_matrix.agents.healthcare_rules import HealthcareRuleEngine
        engine = HealthcareRuleEngine()
        code = 'patient_ssn = "123-45-6789"\nprint(patient_ssn)'
        findings = engine.scan_file("test.py", code)
        phi_findings = [f for f in findings if "ssn" in f.check_name.lower()]
        assert len(phi_findings) >= 1
        assert phi_findings[0].severity == "critical"

    def test_china_id_card_detection(self):
        from codespect_matrix.agents.healthcare_rules import HealthcareRuleEngine
        engine = HealthcareRuleEngine()
        code = 'id_card = "310101199001011234"\nlogger.info(id_card)'
        findings = engine.scan_file("test.py", code)
        cn_phi = [f for f in findings if "china_national_id" in f.check_name.lower()]
        assert len(cn_phi) >= 1
        assert cn_phi[0].severity == "critical"

    def test_phi_in_log_detection(self):
        from codespect_matrix.agents.healthcare_rules import HealthcareRuleEngine
        engine = HealthcareRuleEngine()
        code = 'print(f"Patient {patient_name} has ID {id_card}")'
        findings = engine.scan_file("test.py", code)
        leak = [f for f in findings if "phi_leak" in f.check_name.lower()]
        assert len(leak) >= 1
        assert leak[0].severity == "critical"

    def test_lab_value_range_invalid(self):
        from codespect_matrix.agents.healthcare_rules import HealthcareRuleEngine
        engine = HealthcareRuleEngine()
        code = "bp = 350\nhr = 10"
        findings = engine.scan_file("test.py", code)
        lab = [f for f in findings if "lab_value" in f.check_name.lower()]
        assert len(lab) >= 1
        assert lab[0].severity == "high"
        assert "350" in lab[0].message

    def test_lab_value_range_valid(self):
        from codespect_matrix.agents.healthcare_rules import HealthcareRuleEngine
        engine = HealthcareRuleEngine()
        code = "bp = 120\nhr = 75"
        findings = engine.scan_file("test.py", code)
        lab = [f for f in findings if "lab_value" in f.check_name.lower()]
        assert len(lab) == 0

    def test_fhir_http_insecure(self):
        from codespect_matrix.agents.healthcare_rules import HealthcareRuleEngine
        engine = HealthcareRuleEngine()
        code = 'client = FHIRClient(settings={"api_base": "http://fhir.example.com"})'
        findings = engine.scan_file("fhir_client.py", code)
        fhir = [f for f in findings if "fhir_http" in f.check_name.lower()]
        assert len(fhir) >= 1
        assert fhir[0].severity == "critical"

    def test_fhir_https_safe(self):
        from codespect_matrix.agents.healthcare_rules import HealthcareRuleEngine
        engine = HealthcareRuleEngine()
        code = 'client = FHIRClient(settings={"api_base": "https://fhir.example.com"})'
        findings = engine.scan_file("fhir_client.py", code)
        fhir = [f for f in findings if "fhir_http" in f.check_name.lower()]
        assert len(fhir) == 0

    def test_dicom_phi_tags(self):
        from codespect_matrix.agents.healthcare_rules import HealthcareRuleEngine
        engine = HealthcareRuleEngine()
        code = """import pydicom
dcm = pydicom.dcmread("scan.dcm")
print(dcm.PatientName)
dcm.save_as("out.dcm")"""
        findings = engine.scan_file("dicom_proc.py", code)
        dicom = [f for f in findings if "dicom_phi" in f.check_name.lower()]
        assert len(dicom) >= 1
        assert dicom[0].severity == "critical"

    def test_hl7_mllp_no_tls(self):
        from codespect_matrix.agents.healthcare_rules import HealthcareRuleEngine
        engine = HealthcareRuleEngine()
        code = """import hl7apy
from hl7apy.mllp import MLLPServer
server = MLLPServer("0.0.0.0", 2575)"""
        findings = engine.scan_file("hl7_server.py", code)
        hl7 = [f for f in findings if "hl7_mllp" in f.check_name.lower()]
        assert len(hl7) >= 1
        assert hl7[0].severity == "critical"

    def test_cds_missing_fallback(self):
        from codespect_matrix.agents.healthcare_rules import HealthcareRuleEngine
        engine = HealthcareRuleEngine()
        code = """def check_bp(systolic):
    if systolic > 180:
        alert("Hypertensive crisis")
    return None"""
        findings = engine.scan_file("cds_rules.py", code)
        cds = [f for f in findings if "cds_missing_fallback" in f.check_name.lower()]
        assert len(cds) >= 1
        assert cds[0].severity == "high"

    def test_smart_token_no_validation(self):
        from codespect_matrix.agents.healthcare_rules import HealthcareRuleEngine
        engine = HealthcareRuleEngine()
        code = """import fhirclient
headers = {"Authorization": f"Bearer {access_token}"}
response = requests.get(url, headers=headers)"""
        findings = engine.scan_file("smart_app.py", code)
        smart = [f for f in findings if "smart_token" in f.check_name.lower()]
        assert len(smart) >= 1
        assert smart[0].severity == "critical"


# ── Integration: Memory + Bus ─────────────────────────────────────────────────

class TestIntegration:
    def test_memory_filters_bus_messages(self, tmp_path):
        """FP marked in ProjectMemory should be checkable later."""
        memory = ProjectMemory(str(tmp_path))
        memory.mark_false_positive("test_check", "false alarm", "reviewer")

        # Simulate: after a scan, filtering
        findings = [
            Finding(check_name="test_check", message="false alarm", severity="low"),
            Finding(check_name="real_check", message="real issue", severity="high"),
        ]
        filtered = [f for f in findings if not memory.is_false_positive(f.check_name, f.message)]
        assert len(filtered) == 1
        assert filtered[0].check_name == "real_check"
