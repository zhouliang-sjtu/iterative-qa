# Changelog

All notable changes to codespect-matrix will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2026-06-17

### Changed
- **All-in Architecture**: Removed agent scoring/selective activation (`_select_agents()`). All 24 agents now run unconditionally, leveraging the full rule engine + LLM agent + CPG taint analysis suite in every scan.
- **LinterAgent**: Direct Ruff JSON parsing replaces LLM-interpreted text output. All 283 Ruff rules are now absorbed into codespect findings with proper severity mapping (S→critical, E→high, W→medium). Removes ~15s LLM overhead per lint run.
- **SecurityAgent**: Deterministic healthcare rule engine scan replaces LLM-only fallback. Zero-miss detection for SQL injection, weak crypto, PHI leaks, and unvalidated input patterns.
- **Healthcare Rules**: +5 new security rules — insecure_cipher_ecb, insecure_cipher_rc4, insecure_cipher_des, unvalidated_web_input, unvalidated_type_cast_medical. Total: 104 deterministic rules.
- **LLM Service**: Default model upgraded from qwen-plus to qwen-coder-plus. Added explicit `dashscope.api_key` initialization.
- **Context Size**: Agent context limit expanded from 30KB to 200KB to prevent file truncation during large project scans.
- **Subprocess Compatibility**: All linter subprocess calls unified to `sys.executable -m` for Windows compatibility.
- **Version**: 2.0.0 → 3.0.0

### Fixed
- LinterAgent: `fix_info = diag.get("fix") or {}` guards against `NoneType` crash when Ruff fix field is null
- LinterAgent: `encoding="utf-8", errors="replace"` on Ruff subprocess to prevent GBK decode errors on Windows
- LinterAgent: `_run_mypy` changed from bare `mypy` command to `sys.executable -m mypy`

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
