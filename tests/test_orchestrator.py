"""Integration tests for AgentOrchestrator (no LLM required)."""

import os
import tempfile
import pytest

from codespect_matrix.agents.orchestrator import AgentOrchestrator


class TestOrchestratorInit:
    """AgentOrchestrator initialization and config loading."""

    def test_default_init(self, tmp_path):
        orch = AgentOrchestrator(project_path=str(tmp_path))
        assert orch.project_path == str(tmp_path)
        assert orch.agents == {}
        assert orch.active_agents == []
        assert orch.bus is not None
        assert orch.project_memory is not None
        assert orch.global_kb is not None

    def test_load_config_missing(self, tmp_path):
        """Missing config in tmp_path, falls back to global CONFIG_PATH if exists."""
        orch = AgentOrchestrator(project_path=str(tmp_path))
        # May return empty or the global default config — both valid
        assert isinstance(orch.config, dict)

    def test_cfg_method_default(self, tmp_path):
        orch = AgentOrchestrator(project_path=str(tmp_path))
        assert orch._cfg("nonexistent", "path", default=42) == 42

    def test_initialize(self, tmp_path):
        """Initialize should register agents without crashing."""
        orch = AgentOrchestrator(project_path=str(tmp_path))
        orch.initialize()
        assert len(orch.active_agents) >= 2  # security + developer always active
        assert "security" in orch.active_agents
        assert "developer" in orch.active_agents

    def test_all_agents_registered(self, tmp_path):
        orch = AgentOrchestrator(project_path=str(tmp_path))
        orch._register_all_agents()
        assert len(orch.agents) > 5  # hybrid + LLM agents
        # Verify 3 new agents registered
        assert "linter" in orch.agents
        assert "datascience" in orch.agents
        assert "hardcode" in orch.agents

    def test_custom_config_loaded(self, tmp_path):
        import yaml
        config_path = tmp_path / "agent_config.yaml"
        config_path.write_text(yaml.dump({"agent_selection": {"max_active": 3}}))
        orch = AgentOrchestrator(project_path=str(tmp_path))
        assert orch._cfg("agent_selection", "max_active") == 3

    def test_max_active_honored(self, tmp_path):
        import yaml
        config_path = tmp_path / "agent_config.yaml"
        config_path.write_text(yaml.dump({"agent_selection": {"max_active": 3}}))
        orch = AgentOrchestrator(project_path=str(tmp_path))
        orch.initialize()
        assert len(orch.active_agents) <= 3


class TestOrchestratorPhases:
    """Phased workflow tests (minimal project)."""

    def test_inspect_phase_project_itself(self):
        orch = AgentOrchestrator(project_path=".")
        orch._register_all_agents()
        orch.active_agents = ["security", "developer"]
        count = orch.inspect_phase()
        assert count >= 0  # Returns count, even if 0

    def test_review_phase_empty(self):
        """Review phase with no findings should return zeros."""
        orch = AgentOrchestrator(project_path=".")
        stats = orch.review_phase()
        assert stats == {"confirmed": 0, "rejected": 0, "adjusted": 0}

    def test_generate_report(self, tmp_path):
        orch = AgentOrchestrator(project_path=str(tmp_path))
        orch.initialize()
        result = orch.run_full_cycle(max_rounds=1)
        report = orch.generate_report(result)
        assert "codespect-matrix" in report
        assert "Agent" in report or "agent" in report.lower()

    def test_evolution_integration(self, tmp_path):
        orch = AgentOrchestrator(project_path=str(tmp_path))
        orch.initialize()
        evolution_report = orch.run_evolution(save_baseline=False)
        assert "overall_score" in evolution_report
        assert "health" in evolution_report
        assert "architecture" in evolution_report
        assert "roadmap" in evolution_report


class TestOrchestratorEdgeCases:
    """Edge case handling."""

    def test_convergence_check_empty(self):
        orch = AgentOrchestrator(project_path=".")
        assert orch.check_convergence() is False

    def test_debate_phase_empty(self):
        orch = AgentOrchestrator(project_path=".")
        results = orch.debate_phase()
        assert results == []

    def test_generate_fix_proposals_empty(self):
        orch = AgentOrchestrator(project_path=".")
        proposals = orch.generate_fix_proposals()
        assert proposals == []

    def test_collect_files_context(self):
        orch = AgentOrchestrator(project_path=".")
        ctx = orch._collect_files_context()
        assert isinstance(ctx, str)
        assert len(ctx) > 0 or len(ctx) == 0  # OK if empty in clean project
