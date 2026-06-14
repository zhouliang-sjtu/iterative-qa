# Changelog

All notable changes to codespect-matrix will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-14

### Added
- 16-agent multi-agent architecture: SecurityAgent, HealthcareAgent, PHIAgent, DeveloperAgent, ArchitectAgent, PerformanceAgent, DevOpsAgent, TestAgent, APIAgent, DependencyAgent, ConcurrencyAgent, LinterAgent, DatascienceAgent, HardcodeAgent, ComplianceAgent, MedicalDataAgent
- Debate-style review workflow: Inspect → Cross-review → Debate → Converge → Fix
- Hybrid engine: Rule+LLM for security/healthcare/PHI/compliance; pure LLM for others
- Dual memory: ProjectMemory (`.codespect_matrix_agent_memory.json`) + GlobalKnowledgeBase (`~/.codespect_matrix_knowledge/`)
- Agent communication bus with broadcast/point-to-point messaging
- AI autonomous fix: `--fix-plan` → `--fix-execute` two-step workflow
- **Code Evolution Platform**: 6 analysis engines — HealthScorer, TechDebtAnalyzer, ArchitectureAnalyzer, TestCoverageEstimator, EvolutionReporter, EvolutionBaseline
- `--evolve` / `--evolve-baseline` CLI flags for health dashboard + roadmap
- `--ci` / `--json` CLI flags for CI/CD gate mode
- `agent_config.yaml` runtime configuration
- `locales/{en,zh}/messages.json` i18n infrastructure
- `README_zh.md` Chinese documentation
- 82 pytest tests (37% coverage core agent modules, 76-100% for bus/base/orchestrator/evolution)
- Python 3.10+ support

### Changed
- Architecture: standalone agent platform (removed skill/rule-engine dual-mode)
- CLI: function-based dispatch, agent mode is the default
- LLM temperature: centralized `DEFAULT_ANALYSIS_TEMPERATURE = 0.2` constant
- `.gitignore`: added secrets patterns (`*.p12`, `id_rsa*`, coverage artifacts)
- `setup.py`: Development Status `5 - Production/Stable`

### Usage
```bash
# Multi-agent review (default)
codespect-matrix

# CI gate
codespect-matrix --ci --json

# Code evolution analysis
codespect-matrix --evolve
codespect-matrix --evolve-baseline
```
