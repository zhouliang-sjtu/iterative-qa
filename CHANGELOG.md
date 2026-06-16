# Changelog

All notable changes to codespect-matrix will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-06-17

### Added
- **CPG Deep Taint Analysis** (`cpg_analyzer.py`): AST + Call Graph + Data Flow + Taint analysis, pure Python implementation. Tracks untrusted input → dangerous sink paths across functions. Detects SQL injection, PHI flow, path traversal, and cross-function vulnerability chains.
- **Harness Engineering Layer** (`harness.py`): Constraint enforcement, cross-phase verification, feedback routing, automatic agent error recovery, and quality drift detection ("Agent = Model + Harness" paradigm).
- **10-Stage Pipeline**: CPG Pre-scan → Agent Selection → Parallel Inspection → Harness Validation → Cross-Review → Harness Verification → Debate Arbitration → Convergence Detection → Drift Detection → Fix Generation → Evolution Report.
- **Dynamic Analysis Agents** (`dynamic_agents.py`): DBCompatibilityAgent (SQL dialect mismatch), DBSchemaAgent (ORM vs Schema consistency), APIContractAgent (OpenAPI/parameter validation), SmokeTestAgent (endpoint health checks). All agents use `self.project_profile` for consistent interface.
- **Medical Rule Expansion**: New `healthcare_rules.py` with CDS (Clinical Decision Support), DICOM tag validation, HL7 message security, FHIR resource compliance rules.
- **LLM Judge** (`llm_judge.py`): LLM-based cross-domain review judge for higher quality debate arbitration.
- **round-centric Report Structure** (`report_generator.py`): Comprehensive round-by-round report generation with score dimensions, round reports, and evolution summaries.
- **Dynamic Feature Detection** (`scanner.py`, `models.py`): Project scanner now detects database type, ORM models, API frameworks, OpenAPI schemas, and service runtime status for intelligent agent activation.

### Changed
- **Architecture**: 5-phase → 10-stage pipeline with CPG pre-scan and Harness verification.
- **Agent Interface**: Dynamic agents now use `self.project_profile` / `self.project_path` instead of `project_features` dict parameter, aligned with `BaseAgent.set_context()`.
- **Orchestrator**: Full pipeline now includes CPG scan, Harness validation phases, drift detection, and evolution reporting.
- **CLI**: Enhanced round-centric report output, dynamic agent support, healthcare rule integration.
- **Tests**: 112 tests (up from 82), covering CPG analysis, Harness engine, dynamic agents, healthcare rules, and orchestrator phases.
- **Configuration**: `agent_config.yaml` max_active increased to 16 to accommodate dynamic analysis agents.
- **Version**: 1.0.0 → 2.0.0

### Fixed
- Dynamic agent `inspect()`/`review()`/`generate_fix()`/`can_activate()` signature mismatch with BaseAgent (caused runtime crashes when select as reviewer).

## [1.0.0] - 2026-06-16

### Added
- 16-agent multi-agent architecture: SecurityAgent, HealthcareAgent, PHIAgent, DeveloperAgent, ArchitectAgent, PerformanceAgent, DevOpsAgent, TestAgent, APIAgent, DependencyAgent, ConcurrencyAgent, LinterAgent, DatascienceAgent, HardcodeAgent, ComplianceAgent, MedicalDataAgent
- Debate-style review workflow: Inspect → Cross-review → Debate → Converge → Fix
- Hybrid engine: Rule+LLM for security/healthcare/PHI/compliance; pure LLM for others
- Dual memory: ProjectMemory (`.codespect_matrix_agent_memory.json`) + GlobalKnowledgeBase (`~/.codespect_matrix_knowledge/`)
- Agent communication bus with broadcast/point-to-point messaging
- AI autonomous fix: `--fix-plan` → `--fix-execute` two-step workflow
- **Code Evolution Platform**: 6 engines — HealthScorer, TechDebtAnalyzer, ArchitectureAnalyzer, TestCoverageEstimator, EvolutionReporter, EvolutionBaseline
- **Self-Evolution Engine (SelfEvolver)**: Learns from QA → Fix → Re-QA cycles across projects. Tracks fix effectiveness per check, agent performance by severity, fix confidence scoring, and automatic pattern promotion/pruning
- `--evolve` / `--evolve-baseline` / `--evolve-self` CLI flags
- `--ci` / `--json` CLI flags for CI/CD gate mode
- `agent_config.yaml` runtime configuration
- `locales/{en,zh}/messages.json` i18n infrastructure
- `README_zh.md` Chinese documentation
- 82 pytest tests (59% coverage overall, agent core 76-100%)
- Python 3.10+ support

### Changed
- Architecture: standalone agent platform (removed skill/rule-engine dual-mode)
- CLI: function-based dispatch, agent mode is the default
- LLM temperature: centralized `DEFAULT_ANALYSIS_TEMPERATURE = 0.2` constant
- `.gitignore`: added secrets patterns, coverage artifacts, runtime files, knowledge base
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

# Self-evolution summary
codespect-matrix --evolve-self
```
