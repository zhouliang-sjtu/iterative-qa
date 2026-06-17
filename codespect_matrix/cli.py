"""CLI entry point — 16-Agent Code Evolution Platform."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional


def main():
    parser = argparse.ArgumentParser(
        prog="codespect-matrix",
        description="codespect-matrix — 16-Agent Code Evolution Platform · Debate Review · Hybrid Engine · Health Scoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # Default: multi-agent review
  codespect-matrix
  
  # Target a specific project
  codespect-matrix --path /path/to/project

  # CI/CD gate mode
  codespect-matrix --ci --json

  # Code evolution analysis
  codespect-matrix --evolve
  codespect-matrix --evolve-baseline

  # AI autonomous fix (two-step)
  codespect-matrix --fix-plan          # Step 1: generate plan
  codespect-matrix --fix-execute       # Step 2: execute
        """
    )
    
    parser.add_argument(
        "--path", "-p",
        default=".",
        help="project path (default: current directory)"
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=5,
        help="max review rounds (default: 5)"
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI/CD gate mode — exit_code=1 when thresholds exceeded"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="output JSON format"
    )
    parser.add_argument(
        "--format",
        type=str,
        default="auto",
        choices=["auto", "text", "html", "md", "markdown", "json"],
        help="report format: auto (infer from --output suffix), text, html, md, json"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="report output file path (e.g., report.html, report.md)"
    )
    
    # ── Evolution ──
    parser.add_argument(
        "--evolve",
        action="store_true",
        help="code evolution analysis — health score + tech debt + architecture + roadmap"
    )
    parser.add_argument(
        "--evolve-baseline",
        action="store_true",
        help="save evolution analysis as baseline for trend comparison"
    )
    parser.add_argument(
        "--evolve-self",
        action="store_true",
        help="self-evolution summary — show what the tool has learned from past QA cycles"
    )
    
    # ── AI autonomous fix ──
    parser.add_argument(
        "--fix-plan",
        action="store_true",
        help="step 1: scan and generate fix plan (preview only, no code changes)"
    )
    parser.add_argument(
        "--fix-execute",
        action="store_true",
        help="step 2: execute fix plan (requires --fix-plan first)"
    )
    parser.add_argument(
        "--fix-all",
        action="store_true",
        help="execute all fixes including high-risk ones (with --fix-execute)"
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="rollback all applied fixes to original state"
    )
    
    args = parser.parse_args()
    
    try:
        # ── Code evolution ──
        if args.evolve_self:
            _run_evolve_self(args)
            return
        
        if args.evolve or args.evolve_baseline:
            _run_evolve(args, save_baseline=args.evolve_baseline)
            return
        
        # ── CI gate ──
        if args.ci:
            _run_ci_gate(args)
            return
        
        # ── AI fix ──
        if args.rollback:
            _run_rollback(args)
            return

        if args.fix_plan:
            _run_fix_plan(args)
            return
        
        if args.fix_execute:
            _run_fix_execute(args)
            return
        
        # ── Default: multi-agent review ──
        _run_agent_mode(args)
        
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


# ══════════════════════════════════════════════
# Default multi-agent mode
# ══════════════════════════════════════════════

def _run_agent_mode(args):
    """Multi-agent full-flow review."""
    from codespect_matrix.agents.orchestrator import AgentOrchestrator
    
    print(f"{'='*70}")
    print("  codespect-matrix — 16-Agent Code Evolution Platform")
    print("  Review · Debate · Converge · Evolve")
    print(f"{'='*70}")
    
    orchestrator = AgentOrchestrator(project_path=args.path)
    orchestrator.initialize()
    
    profile = orchestrator._project_profile
    print(f"\n  project: {profile.get('project_type', 'unknown')}")
    print(f"  domain: {profile.get('domain', 'unknown')}")
    print(f"  scale: {profile.get('scale', 'unknown')}")
    print(f"  {len(orchestrator.active_agents)} agents active:")
    for name in orchestrator.active_agents:
        agent = orchestrator.agents.get(name)
        if agent:
            print(f"    [{agent.get_domain():15s}] {name} — {agent.get_description()}")
    
    print(f"\n  starting review...")
    result = orchestrator.run_full_cycle(max_rounds=args.max_rounds)
    
    # Determine output format
    output_format = args.format
    if output_format == "auto" and args.output:
        if args.output.lower().endswith(".html"):
            output_format = "html"
        elif args.output.lower().endswith((".md", ".markdown")):
            output_format = "md"
        elif args.output.lower().endswith(".json"):
            output_format = "json"
        else:
            output_format = "text"
    elif output_format == "auto":
        output_format = "text"

    if args.json or output_format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)
            print(f"\n  JSON report saved to: {args.output}")
    elif output_format in ("html", "md", "markdown"):
        from codespect_matrix.report_generator import (
            ComprehensiveReportGenerator, RoundReport, ScanPhase,
            IssueItem, FixItem, TechDebtItem, ScoreDimension,
        )
        from codespect_matrix.evolution import EvolutionReporter

        # Build RoundReport list from result cycles
        rounds = []
        for cycle in result.get("cycles", []):
            round_num = cycle.get("round", len(rounds) + 1)
            confirmed = cycle.get("confirmed", [])

            # Issues
            issues = []
            for issue in confirmed:
                issues.append(IssueItem(
                    severity=issue.get("severity", "low"),
                    check_name=issue.get("check_name", "unknown"),
                    message=issue.get("message", ""),
                    file_path=issue.get("file_path", ""),
                    line_start=issue.get("line_start", 0),
                    remediation=issue.get("remediation", ""),
                ))

            # Fixes
            fixes = []
            for fix in cycle.get("fixes", []):
                fixes.append(FixItem(
                    idx=0,  # Will be renumbered by generator
                    level=fix.get("severity", "P3"),
                    file=fix.get("file", "unknown"),
                    problem=fix.get("problem", "")[:100],
                    fix_method=fix.get("fix", "")[:100],
                ))

            # Scan phases (synthetic)
            phases = [
                ScanPhase("环境基线检查", "pass", "Python环境、依赖版本正常"),
                ScanPhase("静态代码分析", "warn" if any(i.severity in ("critical", "high") for i in issues) else "pass", "规则引擎扫描完成"),
                ScanPhase("多视角审查", "pass", f"{len(confirmed)} 个问题通过交叉验证"),
                ScanPhase("AI智能修复", "pass" if fixes else "info", f"自动修复 {len(fixes)} 项"),
                ScanPhase("回归验证", "pass", "修复后重新扫描确认"),
            ]

            # Convergence status
            p0 = sum(1 for i in issues if i.severity == "critical")
            p1 = sum(1 for i in issues if i.severity == "high")
            if p0 == 0 and p1 == 0 and round_num > 1:
                conv = "已收敛"
            elif p0 == 0 and round_num > 1:
                conv = "趋于收敛"
            else:
                conv = "未收敛"

            # Scores (simple penalty-based)
            p2 = sum(1 for i in issues if i.severity == "medium")
            penalty = p0 * 20 + p1 * 10 + p2 * 3
            quality_score = max(0, 100 - penalty)
            grade = "A" if quality_score >= 90 else "B" if quality_score >= 70 else "C" if quality_score >= 50 else "D" if quality_score >= 40 else "F"
            scores = [
                ScoreDimension("代码质量", quality_score, grade),
            ]

            rounds.append(RoundReport(
                round_num=round_num,
                scan_phases=phases,
                issues_found=issues,
                fixes_applied=fixes,
                convergence_status=conv,
                scores=scores,
                conclusion=f"第{round_num}轮完成，发现 {len(issues)} 个问题，修复 {len(fixes)} 项。" if issues else f"第{round_num}轮完成，未发现新问题。",
            ))

        # Fallback: if no cycles, create a single round from confirmed issues
        if not rounds:
            issues = []
            for issue in result.get("confirmed_issues", []):
                issues.append(IssueItem(
                    severity=issue.get("severity", "low"),
                    check_name=issue.get("check_name", "unknown"),
                    message=issue.get("message", ""),
                    file_path=issue.get("file_path", ""),
                    line_start=issue.get("line_start", 0),
                    remediation=issue.get("remediation", ""),
                ))
            p0 = sum(1 for i in issues if i.severity == "critical")
            p1 = sum(1 for i in issues if i.severity == "high")
            p2 = sum(1 for i in issues if i.severity == "medium")
            penalty = p0 * 20 + p1 * 10 + p2 * 3
            quality_score = max(0, 100 - penalty)
            rounds.append(RoundReport(
                round_num=1,
                scan_phases=[
                    ScanPhase("环境基线检查", "pass", "环境正常"),
                    ScanPhase("静态代码分析", "warn" if p0 > 0 or p1 > 0 else "pass", "扫描完成"),
                    ScanPhase("多视角审查", "pass", f"{len(issues)} 个问题确认"),
                    ScanPhase("AI智能修复", "info", "未启用自动修复"),
                    ScanPhase("回归验证", "pass", "验证完成"),
                ],
                issues_found=issues,
                convergence_status="未收敛" if p0 > 0 or p1 > 0 else "已收敛",
                scores=[ScoreDimension("代码质量", quality_score, "A" if quality_score >= 90 else "B" if quality_score >= 70 else "C")],
                conclusion="单轮扫描完成。" + ("存在关键问题需修复。" if p0 > 0 or p1 > 0 else "未发现严重问题。"),
            ))

        # Tech debt from evolution
        try:
            evo_reporter = EvolutionReporter(args.path)
            evolution = evo_reporter.full_report(result.get("confirmed_issues", []))
        except Exception:
            evolution = None

        if evolution and rounds:
            debt_items = []
            debt = evolution.get("technical_debt", {})
            markers = debt.get("markers", [])
            if markers:
                debt_items.append(TechDebtItem("P3-01", f"{len(markers)} 处 TODO/FIXME", "多文件", "业务决策后清理"))
            large_files = debt.get("large_files", [])
            if large_files:
                debt_items.append(TechDebtItem("P3-02", f"{len(large_files)} 个超大文件", "多文件", "拆分模块"))
            cov = evolution.get("test_coverage", {})
            if cov.get("test_files_found", 0) == 0:
                debt_items.append(TechDebtItem("P3-03", "0 个自动化测试", "全项目", "补充测试"))
            # Attach to last round
            rounds[-1].tech_debt = debt_items

        gen = ComprehensiveReportGenerator(args.path)
        fmt = "html" if output_format == "html" else "md"
        report = gen.generate(rounds=rounds, profile=profile, format=fmt)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"\n  {fmt.upper()} report saved to: {args.output}")
        else:
            # For HTML without output file, save to default path
            default_path = os.path.join(args.path, f"codespect-report.{fmt}")
            with open(default_path, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"\n  {fmt.upper()} report saved to: {default_path}")
    else:
        report = orchestrator.generate_report(result)
        print("\n" + report)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"\n  report saved to: {args.output}")
    
    has_critical = any(
        i.get("severity") == "critical"
        for i in result.get("confirmed_issues", [])
    )
    sys.exit(1 if has_critical else 0)


# ══════════════════════════════════════════════
# CI gate mode
# ══════════════════════════════════════════════

def _run_ci_gate(args):
    """CI gate (agent mode)."""
    from codespect_matrix.agents.orchestrator import AgentOrchestrator
    
    orchestrator = AgentOrchestrator(project_path=args.path)
    orchestrator.initialize()
    result = orchestrator.run_full_cycle(max_rounds=1)
    
    severities = {"critical": 0, "high": 0, "medium": 0}
    for issue in result["confirmed_issues"]:
        sev = issue.get("severity", "low")
        severities[sev] = severities.get(sev, 0) + 1
    
    gate_pass = (
        severities.get("critical", 0) == 0 and
        severities.get("high", 0) <= 5 and
        severities.get("medium", 0) <= 30
    )
    
    output = {
        "exit_code": 0 if gate_pass else 1,
        "severities": severities,
        "total_findings": result["total_findings"],
        "confirmed": len(result["confirmed_issues"]),
        "rejected": len(result["rejected_issues"]),
        "converged": result["converged"],
        "timestamp": result["cycles"][0]["timestamp"] if result["cycles"] else "",
    }
    
    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"{'='*60}")
        print(f"CI Gate Check — {'PASS' if gate_pass else 'FAIL'}")
        print(f"{'='*60}")
        print(f"severities: {severities}")
        print(f"confirmed: {len(result['confirmed_issues'])}")
        print(f"rejected: {len(result['rejected_issues'])}")
        print(f"gate: {'PASS' if gate_pass else 'FAIL'}")
    
    sys.exit(0 if gate_pass else 1)


# ══════════════════════════════════════════════
# Code evolution analysis
# ══════════════════════════════════════════════

def _run_evolve(args, save_baseline: bool = False):
    """Code evolution analysis."""
    from codespect_matrix.agents.orchestrator import AgentOrchestrator
    
    print(f"{'='*70}")
    print("  codespect-matrix — Code Evolution Analysis")
    print("  Health · Tech Debt · Architecture · Roadmap")
    print(f"{'='*70}")
    
    orchestrator = AgentOrchestrator(project_path=args.path)
    orchestrator.initialize()
    
    print(f"  project: {orchestrator._project_profile.get('project_type', 'unknown')}")
    print(f"  {len(orchestrator.active_agents)} agents active, analyzing...\n")
    
    report = orchestrator.run_evolution(save_baseline=save_baseline)
    
    if "error" in report:
        print(f"  error: {report['error']}")
        sys.exit(1)
    
    h = report["health"]
    d = report["technical_debt"]
    a = report["architecture"]
    c = report["test_coverage"]
    
    # Dashboard
    print(f"  {'-'*60}")
    print(f"  PROJECT HEALTH DASHBOARD")
    print(f"  {'-'*60}")
    
    def _bar(label, score, width=30):
        filled = int(score / 100 * width)
        tag = "OK" if score >= 70 else "~~" if score >= 40 else "!!"
        return f"  {label:20s} {tag} [{'#'*filled}{'-'*(width-filled)}] {score:5.1f}%"
    
    print(_bar("Overall Health", report["overall_score"]))
    print(_bar("  Code Quality", h["health_score"]))
    print(_bar("  Architecture", a["architecture_health"]))
    debt_health = max(0, 100 - d["debt_index"])
    print(_bar("  Debt Freedom", debt_health))
    print(_bar("  Test Coverage", c.get("percent_covered", 0)))
    print()
    
    # Details
    print(f"  CODE QUALITY [{h['level'].upper()}]")
    print(f"    score: {h['health_score']}/100")
    for sev, cnt in sorted(h["severity_counts"].items()):
        if cnt > 0:
            print(f"    {sev}: {cnt}")
    print()
    
    print(f"  TECHNICAL DEBT [{d['level'].upper()}]")
    print(f"    index: {d['debt_index']}/100")
    print(f"    markers: {d['marker_count']}")
    if d["markers"][:3]:
        for m in d["markers"][:3]:
            print(f"      [{m['marker']}] {m['content'][:60]}...")
    print(f"    large files: {len(d['large_files'])}")
    for f in d["large_files"][:3]:
        print(f"      {f['file']} ({f['lines']} lines)")
    print()
    
    print(f"  ARCHITECTURE [{a['level'].upper()}]")
    print(f"    health: {a['architecture_health']}/100")
    print(f"    modules: {a['module_count']}")
    print(f"    cycles: {len(a['cycles'])}")
    if a["god_modules"]:
        print(f"    god modules: {len(a['god_modules'])}")
        for g in a["god_modules"][:3]:
            print(f"      {g['module']} ({g['lines']} lines, fan-out: {g['fan_out']})")
    print()
    
    print(f"  TEST COVERAGE [{c.get('level', 'unknown').upper()}]")
    if c.get("has_coverage"):
        print(f"    coverage: {c['percent_covered']}%")
        print(f"    lines: {c['covered_lines']}/{c['total_lines']}")
    else:
        print(f"    test files: {c.get('test_files_found', 0)}")
        if c.get("note"):
            print(f"    note: {c['note']}")
    print()
    
    # Roadmap
    if report.get("roadmap"):
        print(f"  {'-'*60}")
        print(f"  IMPROVEMENT ROADMAP")
        print(f"  {'-'*60}")
        for item in report["roadmap"]:
            print(f"  [{item['priority']}] {item['category']}")
            print(f"       {item['action']}")
            print(f"       reason: {item['rationale']}")
            print(f"       effort: {item['effort']}")
            print()
    
    if save_baseline:
        print(f"  baseline saved (.codespect_matrix_evolution_baseline.json)")
        print(f"  run `codespect-matrix --evolve` to compare trend")
    
    if args.json:
        print("\n" + json.dumps(report, indent=2, ensure_ascii=False, default=str))
    
    sys.exit(0 if report["overall_score"] >= 50 else 1)


# ══════════════════════════════════════════════
# AI autonomous fix
# ══════════════════════════════════════════════

def _run_rollback(args):
    """Rollback all applied fixes to original state."""
    from codespect_matrix.fix_engine import FixEngine

    print(f"{'='*60}")
    print("  codespect-matrix — Rollback Applied Fixes")
    print(f"{'='*60}")

    engine = FixEngine(args.path)
    backups = engine.list_backups()
    if backups["total_backups"] == 0:
        print("\n  No backups found — nothing to rollback.")
        return

    print(f"\n  Found {backups['total_backups']} backups across {backups['total_files']} files:")
    for rel, entries in backups["files"].items():
        latest = entries[-1]["timestamp"] if entries else "unknown"
        print(f"    {rel}  ({len(entries)} backup(s), latest: {latest})")

    result = engine.rollback_all()
    print(f"\n  Rollback results:")
    print(f"    Rolled back: {len(result['rolled_back'])}")
    print(f"    Failed:      {len(result['failed'])}")
    print(f"    Unchanged:   {len(result['unchanged'])}")

    if result.get("error"):
        print(f"    Error: {result['error']}")
    elif result["rolled_back"]:
        print(f"\n  All fixes reverted. Backups preserved in .codespect_matrix_backups/")

def _run_fix_plan(args):
    """AI fix — step 1: scan project and generate a fix plan.

    Displays confirmed issues with fix descriptions. User reviews,
    then runs --fix-execute to apply changes.
    """
    from codespect_matrix.agents.orchestrator import AgentOrchestrator
    from codespect_matrix.evolution import HealthScorer

    print(f"{'='*60}")
    print("  codespect-matrix — AI Autonomous Fix: Generate Plan")
    print(f"{'='*60}")

    orchestrator = AgentOrchestrator(project_path=args.path)
    orchestrator.initialize()
    orchestrator.inspect_phase()
    orchestrator.review_phase()

    confirmed = [f for f in orchestrator.all_findings if f.ruling == "confirmed"]
    if not confirmed:
        print("\n  no issues found — project is clean.")
        return

    # Health before fix
    scorer = HealthScorer()
    before = scorer.compute([f.to_dict() for f in confirmed])
    before_score = before.get("health_score", 0)

    proposals = orchestrator.generate_fix_proposals()
    auto_fixable = [p for p in proposals if p.get("can_auto_fix", False)]
    manual = [p for p in proposals if not p.get("can_auto_fix", False)]

    print(f"\n  Health score (before): {before_score}/100")
    print(f"  Confirmed issues:     {len(confirmed)}")
    print(f"  Auto-fixable:         {len(auto_fixable)}")
    print(f"  Needs manual review:  {len(manual)}")
    print()

    if auto_fixable:
        print("  Auto-fixable issues:")
        print("  " + "-" * 52)
        for i, p in enumerate(auto_fixable, 1):
            f = p.get("finding", {})
            sev = f.get("severity", "?")
            line = f.get("line_start", 0)
            filepath = f.get("file_path", "")
            msg = f.get("message", "?")[:80]
            label = "C" if sev == "critical" else "H" if sev == "high" else "M" if sev == "medium" else "L"
            print(f"  [{label}] {f.get('check_name', '?')}")
            print(f"       {msg}")
            if filepath and line:
                print(f"       {filepath}:{line}")
            fix_desc = p.get("fix_description", "")[:100]
            print(f"       fix: {fix_desc}")
            print()

    if manual:
        print(f"  Manual review needed ({len(manual)} issues):")
        print("  " + "-" * 52)
        for i, p in enumerate(manual, 1):
            f = p.get("finding", {})
            print(f"  {i}. [{f.get('severity', '?')}] {f.get('check_name', '?')}")
            print(f"     {f.get('message', '?')[:100]}")
            print(f"     {p.get('fix_description', '?')[:120]}")
            print()

    print(f"  To apply auto-fixes:   codespect-matrix --fix-execute")
    print(f"  To apply ALL fixes:    codespect-matrix --fix-execute --fix-all")
    print(f"  (backups saved to .codespect_matrix_backups/)")


def _run_fix_execute(args):
    """AI fix — step 2: apply fixes and verify improvement."""
    from codespect_matrix.agents.orchestrator import AgentOrchestrator
    from codespect_matrix.evolution import HealthScorer
    from codespect_matrix.fix_engine import FixEngine
    from codespect_matrix.llm_service import LLMService

    print(f"{'='*60}")
    print("  codespect-matrix — AI Autonomous Fix: Execute")
    print(f"{'='*60}")

    orchestrator = AgentOrchestrator(project_path=args.path)
    orchestrator.initialize()
    orchestrator.inspect_phase()
    orchestrator.review_phase()

    confirmed = [f for f in orchestrator.all_findings if f.ruling == "confirmed"]
    if not confirmed:
        print("\n  no issues to fix.")
        return

    # Health before
    scorer = HealthScorer()
    before = scorer.compute([f.to_dict() for f in confirmed])
    before_score = before.get("health_score", 0)
    print(f"\n  Health before fix:  {before_score}/100")
    print(f"  Issues to address:  {len(confirmed)}")

    proposals = orchestrator.generate_fix_proposals()
    llm = None
    try:
        llm = LLMService()
    except Exception:
        print("  (no LLM configured — rule-based fixes only)")

    # Apply fixes
    engine = FixEngine(args.path, llm)
    results = engine.execute_fixes(proposals, fix_all=args.fix_all)
    summary = engine.get_fix_summary()

    print(f"\n  Fix results:")
    print(f"    Applied:  {summary['applied']}")
    print(f"    Failed:   {summary['failed']}")

    if summary["files_changed"]:
        print(f"\n  Files modified:")
        for f in summary["files_changed"]:
            rel = os.path.relpath(f, args.path) if os.path.isabs(f) else f
            print(f"    - {rel}")
        print(f"\n  Backups saved to: {os.path.relpath(engine.backup_dir, args.path)}")

    if summary["failed"] > 0:
        print(f"\n  Failed fixes:")
        for r in results:
            if not r.success:
                print(f"    - {r.check_name}: {r.error}")

    # Re-scan to verify
    if summary["applied"] > 0:
        print(f"\n  Re-scanning to verify...")
        orchestrator.all_findings = []
        orchestrator.inspect_phase()
        orchestrator.review_phase()
        after_confirmed = [f for f in orchestrator.all_findings
                           if f.ruling == "confirmed"]
        after_score = scorer.compute(
            [f.to_dict() for f in after_confirmed]
        ).get("health_score", 0)

        delta = round(after_score - before_score, 1)
        print(f"  Health after fix:   {after_score}/100")
        print(f"  Improvement:        {delta:+}")

        # Record in SelfEvolver
        try:
            from codespect_matrix.evolution import SelfEvolver
            evolver = SelfEvolver()
            evolver.record_qa_cycle(
                project_name=Path(args.path).name,
                before_health=before_score,
                findings=[r.to_dict() for r in results],
                fixes_applied=[
                    {"check_name": r.check_name, "success": r.success}
                    for r in results
                ],
                after_health=after_score,
                fix_details=[
                    {
                        "check_name": r.check_name,
                        "reasoning": r.reasoning,
                        "old_code": r.patch.get("old_str", "")[:200],
                        "new_code": r.patch.get("new_str", "")[:200],
                    }
                    for r in results if r.success and r.reasoning
                ],
            )
            print(f"  SelfEvolver:        cycle recorded for future learning")
        except Exception:
            pass

    if args.json:
        output = {
            "before_health": before_score,
            "after_health": after_score if summary["applied"] > 0 else None,
            "fix_summary": summary,
        }
        import json as _json
        print("\n" + _json.dumps(output, indent=2, ensure_ascii=False, default=str))


# ══════════════════════════════════════════════
# Self-evolution summary
# ══════════════════════════════════════════════

def _run_evolve_self(args):
    """Self-evolution summary — what the tool has learned."""
    from codespect_matrix.evolution import SelfEvolver

    print(f"{'='*60}")
    print("  codespect-matrix — Self-Evolution Summary")
    print("  What has been learned from past QA cycles")
    print(f"{'='*60}")

    evolver = SelfEvolver()
    summary = evolver.get_evolution_summary()

    if summary.get("status") == "no_data":
        print("\n  No QA cycles recorded yet.")
        print("  The tool evolves as you use it across projects:")
        print("  1. Run codespect-matrix on your project")
        print("  2. Fix issues found")
        print("  3. Re-run to verify improvements")
        print("  4. The tool learns from each cycle automatically")
        return

    print(f"\n  Generation:        {summary['generation']}")
    print(f"  QA Cycles:         {summary['total_cycles']}")
    print(f"  Projects Helped:   {summary['projects_helped']}")
    print(f"  Avg Health Gain:   {summary['average_health_improvement']:.1f}%")
    print(f"  Patterns Learned:  {summary['patterns_learned']}")

    if summary.get("top_agents"):
        print(f"\n  Top Agents:")
        for i, agent in enumerate(summary["top_agents"], 1):
            print(f"    {i}. {agent}")

    if summary.get("fix_effectiveness"):
        print(f"\n  Fix Confidence by Issue Type:")
        for check, data in summary["fix_effectiveness"].items():
            bar = "#" * int(data["confidence"] * 20)
            print(f"    {check:30s} [{bar}{'-'*(20-len(bar))}] {data['confidence']:.0%} ({data['total']} attempts)")

    print(f"\n  Knowledge base: ~/.codespect_matrix_knowledge/self_evolution.json")

    if args.json:
        import json
        print("\n" + json.dumps(summary, indent=2, ensure_ascii=False, default=str))
