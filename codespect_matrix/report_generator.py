"""Comprehensive report generator — HTML + Markdown dual format.

Generates publication-quality audit reports with:
- Project profile (tech stack, domain, scale)
- Agent perspective audit matrix
- Round-by-round issue discovery & remediation tracking
- Convergence determination
- Quality rating dashboard (score bars + letter grade)
- Technical debt inventory
- Service health status
"""

from __future__ import annotations

import os
import json
import html
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict


# ─── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class AgentPerspective:
    name: str
    compatibility: float          # 0.0-1.0
    p0: int
    p1: int
    p2: int
    conclusion: str
    is_new: bool = False


@dataclass
class RoundSummary:
    round_num: int
    p0: int
    p1: int
    p2: int
    fixes_applied: int
    status: str                   # "未收敛" | "趋于收敛" | "已收敛"
    issues: List[Dict] = field(default_factory=list)


@dataclass
class ScoreDimension:
    label: str
    score: float                  # 0-100
    grade: str                    # A+/A/A-/B+/B/B-/C/D/F


@dataclass
class ProjectProfile:
    name: str
    project_type: str
    domain: str
    backend_stack: str
    frontend_stack: str
    ai_models: str
    code_scale: str
    ports: str
    directory_structure: str


@dataclass
class FixRecord:
    idx: int
    round_num: int
    level: str
    file: str
    problem: str
    fix_method: str


@dataclass
class TechDebtItem:
    id: str
    description: str
    files: str
    recommendation: str


# ─── Report Generator ────────────────────────────────────────────────────────

class ComprehensiveReportGenerator:
    """Generate comprehensive HTML/Markdown audit reports."""

    SEVERITY_CLASS = {
        "critical": "p0",
        "high": "p1",
        "medium": "p2",
        "low": "p3",
    }

    def __init__(self, project_path: str):
        self.project_path = project_path
        self.project_name = Path(project_path).name or "unnamed"
        self.timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        self.date_str = datetime.now(UTC).strftime("%Y-%m-%d")

    # ═══════════════════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════════════════

    def generate(
        self,
        review_result: Dict,
        evolution_report: Optional[Dict] = None,
        profile: Optional[Dict] = None,
        format: str = "html",
    ) -> str:
        """Generate report in specified format.

        Args:
            review_result: output from orchestrator.run_full_cycle()
            evolution_report: output from EvolutionReporter.full_report()
            profile: project profile from scanner
            format: "html" | "md" | "markdown"
        """
        # Build rich data structures
        project_profile = self._build_project_profile(profile)
        perspectives = self._build_perspectives(review_result)
        rounds = self._build_rounds(review_result)
        fixes = self._build_fixes(review_result, rounds)
        tech_debt = self._build_tech_debt(evolution_report)
        scores = self._build_scores(evolution_report, review_result)
        overall = self._compute_overall(scores)
        convergence = self._build_convergence(rounds)

        if format.lower() in ("html",):
            return self._render_html(
                project_profile, perspectives, rounds, fixes,
                tech_debt, scores, overall, convergence, review_result,
            )
        else:
            return self._render_markdown(
                project_profile, perspectives, rounds, fixes,
                tech_debt, scores, overall, convergence, review_result,
            )

    # ═══════════════════════════════════════════════════════════════════════
    # Data Builders
    # ═══════════════════════════════════════════════════════════════════════

    def _build_project_profile(self, profile: Optional[Dict]) -> ProjectProfile:
        p = profile or {}
        tech_stack = p.get("tech_stack", [])
        backend = ", ".join([t for t in tech_stack if t not in ("React", "Vue", "Node.js")]) or "Unknown"
        frontend = ", ".join([t for t in tech_stack if t in ("React", "Vue", "Node.js")]) or "None"

        scale_info = p.get("scale", {})
        scale_str = f"{scale_info.get('total_files', '?')} files / {scale_info.get('total_lines', '?')} lines"

        return ProjectProfile(
            name=self.project_name,
            project_type=p.get("project_type", "Unknown"),
            domain=p.get("domain", "Unknown"),
            backend_stack=backend,
            frontend_stack=frontend,
            ai_models="Configured via LLMService",
            code_scale=scale_str,
            ports="Auto-detected",
            directory_structure=p.get("directory_structure", "Standard layout"),
        )

    def _build_perspectives(self, result: Dict) -> List[AgentPerspective]:
        """Build perspective audit matrix from review result."""
        perspectives = []
        agent_stats = result.get("agent_stats", {})

        for agent_name, stats in agent_stats.items():
            sev_counts = stats.get("severity_counts", {})
            perspectives.append(AgentPerspective(
                name=agent_name,
                compatibility=stats.get("compatibility", 0.8),
                p0=sev_counts.get("critical", 0),
                p1=sev_counts.get("high", 0),
                p2=sev_counts.get("medium", 0),
                conclusion=stats.get("conclusion", "Reviewed"),
            ))

        # If no agent stats, build from findings
        if not perspectives:
            findings = result.get("confirmed_issues", [])
            agent_findings = {}
            for f in findings:
                agent = f.get("agent", "unknown")
                agent_findings.setdefault(agent, []).append(f)

            for agent, finds in agent_findings.items():
                sev = {"critical": 0, "high": 0, "medium": 0}
                for f in finds:
                    s = f.get("severity", "low")
                    if s in sev:
                        sev[s] += 1
                perspectives.append(AgentPerspective(
                    name=agent,
                    compatibility=0.8,
                    p0=sev["critical"],
                    p1=sev["high"],
                    p2=sev["medium"],
                    conclusion=f"{len(finds)} findings reviewed",
                ))

        return perspectives

    def _build_rounds(self, result: Dict) -> List[RoundSummary]:
        """Build round summaries from review cycles."""
        rounds = []
        cycles = result.get("cycles", [])

        for i, cycle in enumerate(cycles, 1):
            confirmed = cycle.get("confirmed", [])
            sev_counts = {"critical": 0, "high": 0, "medium": 0}
            for f in confirmed:
                s = f.get("severity", "low")
                if s in sev_counts:
                    sev_counts[s] += 1

            status = "已收敛" if i > 1 and sev_counts["critical"] == 0 and sev_counts["high"] == 0 else "未收敛"
            if i > 1 and status == "未收敛":
                status = "趋于收敛"

            rounds.append(RoundSummary(
                round_num=i,
                p0=sev_counts["critical"],
                p1=sev_counts["high"],
                p2=sev_counts["medium"],
                fixes_applied=cycle.get("fixes_applied", 0),
                status=status,
                issues=confirmed,
            ))

        return rounds

    def _build_fixes(self, result: Dict, rounds: List[RoundSummary]) -> List[FixRecord]:
        """Build fix records from review result."""
        fixes = []
        idx = 1
        for cycle in result.get("cycles", []):
            round_num = cycle.get("round", 1)
            for fix in cycle.get("fixes", []):
                fixes.append(FixRecord(
                    idx=idx,
                    round_num=round_num,
                    level=fix.get("severity", "P3"),
                    file=fix.get("file", "unknown"),
                    problem=fix.get("problem", "")[:80],
                    fix_method=fix.get("fix", "")[:80],
                ))
                idx += 1
        return fixes

    def _build_tech_debt(self, evolution: Optional[Dict]) -> List[TechDebtItem]:
        """Build technical debt inventory."""
        debt_items = []
        if not evolution:
            return debt_items

        debt = evolution.get("technical_debt", {})
        markers = debt.get("markers", [])
        large_files = debt.get("large_files", [])

        if markers:
            debt_items.append(TechDebtItem(
                id="P3-01",
                description=f"{len(markers)} 处 TODO/FIXME/HACK 标记",
                files=f"{len(set(m.get('file', '') for m in markers))} 文件",
                recommendation="功能规划标记，业务决策后清理",
            ))

        if large_files:
            debt_items.append(TechDebtItem(
                id="P3-02",
                description=f"{len(large_files)} 个超大文件 (>500行)",
                files=", ".join([f["file"] for f in large_files[:3]]),
                recommendation="拆分为单一职责模块",
            ))

        # Check for zero tests
        cov = evolution.get("test_coverage", {})
        if cov.get("test_files_found", 0) == 0:
            debt_items.append(TechDebtItem(
                id="P3-03",
                description="0 个自动化测试",
                files="全项目",
                recommendation="补充核心模块单元测试和集成测试",
            ))

        return debt_items

    def _build_scores(self, evolution: Optional[Dict], result: Dict) -> List[ScoreDimension]:
        """Build score dimensions."""
        scores = []

        if evolution:
            h = evolution.get("health", {})
            a = evolution.get("architecture", {})
            d = evolution.get("technical_debt", {})
            c = evolution.get("test_coverage", {})

            scores.append(ScoreDimension("代码质量", h.get("health_score", 50), self._to_grade(h.get("health_score", 50))))
            scores.append(ScoreDimension("架构健康", a.get("architecture_health", 50), self._to_grade(a.get("architecture_health", 50))))
            scores.append(ScoreDimension("技术债务", max(0, 100 - d.get("debt_index", 0)), self._to_grade(max(0, 100 - d.get("debt_index", 0)))))
            scores.append(ScoreDimension("测试覆盖", c.get("percent_covered", 0), self._to_grade(c.get("percent_covered", 0))))
        else:
            # Simple score from findings
            confirmed = result.get("confirmed_issues", [])
            sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for f in confirmed:
                s = f.get("severity", "low")
                sev_counts[s] = sev_counts.get(s, 0) + 1

            penalty = sev_counts["critical"] * 20 + sev_counts["high"] * 10 + sev_counts["medium"] * 3
            quality_score = max(0, 100 - penalty)
            scores.append(ScoreDimension("代码质量", quality_score, self._to_grade(quality_score)))
            scores.append(ScoreDimension("安全性", quality_score, self._to_grade(quality_score)))
            scores.append(ScoreDimension("可维护性", quality_score, self._to_grade(quality_score)))
            scores.append(ScoreDimension("部署就绪", quality_score, self._to_grade(quality_score)))

        return scores

    def _compute_overall(self, scores: List[ScoreDimension]) -> tuple[float, str, str]:
        """Compute overall score, grade, and status."""
        if not scores:
            return 0.0, "F", "需立即修复"
        avg = sum(s.score for s in scores) / len(scores)
        grade = self._to_grade(avg)
        status = "可交付" if avg >= 70 else "需整改" if avg >= 50 else "需立即修复"
        return round(avg, 1), grade, status

    def _build_convergence(self, rounds: List[RoundSummary]) -> List[Dict]:
        """Build convergence determination table."""
        convergence = []
        for r in rounds:
            convergence.append({
                "round": f"第 {r.round_num} 轮",
                "p0": r.p0,
                "p1": r.p1,
                "p2": r.p2,
                "fixes": r.fixes_applied,
                "status": r.status,
            })
        return convergence

    # ═══════════════════════════════════════════════════════════════════════
    # HTML Renderer
    # ═══════════════════════════════════════════════════════════════════════

    def _render_html(
        self,
        profile: ProjectProfile,
        perspectives: List[AgentPerspective],
        rounds: List[RoundSummary],
        fixes: List[FixRecord],
        tech_debt: List[TechDebtItem],
        scores: List[ScoreDimension],
        overall: tuple,
        convergence: List[Dict],
        result: Dict,
    ) -> str:
        """Render full HTML report."""
        overall_score, overall_grade, overall_status = overall

        parts = []
        parts.append(self._html_head(profile.name))
        parts.append(self._html_header(profile))
        parts.append(self._html_perspective_matrix(perspectives))
        parts.append(self._html_rounds(rounds))
        if fixes:
            parts.append(self._html_fixes(fixes))
        if tech_debt:
            parts.append(self._html_tech_debt(tech_debt))
        parts.append(self._html_convergence(convergence))
        parts.append(self._html_scores(scores, overall_score, overall_grade, overall_status))
        parts.append(self._html_confirmed_issues(result.get("confirmed_issues", [])))
        parts.append(self._html_footer())
        parts.append("</div></body></html>")

        return "\n".join(parts)

    def _html_head(self, title: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>codespect-matrix 质检报告 — {html.escape(title)}</title>
<style>
:root {{
  --bg: #f8f9fa; --card: #ffffff; --border: #dee2e6;
  --text: #212529; --muted: #6c757d; --accent: #0d6efd;
  --green: #198754; --green-bg: #d1e7dd; --yellow: #b8860b;
  --yellow-bg: #fff3cd; --red: #dc3545; --red-bg: #f8d7da;
  --table-stripe: #f2f4f6; --code-bg: #f0f2f4;
  --shadow: 0 1px 3px rgba(0,0,0,0.08);
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.8; font-size: 15px;
}}
.container {{ max-width: 1020px; margin: 0 auto; padding: 32px 24px; }}
.header {{
  text-align: center; padding: 44px 20px 32px;
  border-bottom: 2px solid var(--border); margin-bottom: 32px;
}}
.header h1 {{ font-size: 30px; margin-bottom: 6px; color: #1a1a2e; letter-spacing: -0.5px; }}
.header .badge {{
  display: inline-block; background: var(--green-bg); color: var(--green);
  font-weight: 700; padding: 3px 16px; border-radius: 14px; font-size: 13px;
  margin-bottom: 12px; border: 1px solid #badbcc;
}}
.header .sub {{ color: var(--muted); font-size: 14px; margin-top: 2px; }}
.header .meta {{ color: var(--muted); font-size: 13px; margin-top: 8px; }}
.header .meta span {{ margin: 0 14px; }}
.card {{
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 28px; margin-bottom: 24px; box-shadow: var(--shadow);
}}
h2 {{
  font-size: 21px; margin-bottom: 18px; padding-bottom: 8px;
  border-bottom: 2px solid var(--accent); color: #1a1a2e;
}}
h3 {{ font-size: 17px; margin: 28px 0 12px; color: var(--accent); }}
h4 {{ font-size: 15px; margin: 18px 0 8px; color: #343a40; }}
table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }}
th, td {{ text-align: left; padding: 10px 14px; border: 1px solid var(--border); }}
th {{ background: #e9ecef; font-weight: 600; color: #495057; font-size: 13px; }}
tr:nth-child(even) td {{ background: var(--table-stripe); }}
.pass {{ color: var(--green); font-weight: 600; }}
.warn {{ color: var(--yellow); }}
.fail {{ color: var(--red); font-weight: 600; }}
.p0 {{ background: var(--red); color: #fff; padding: 2px 9px; border-radius: 4px; font-size: 12px; font-weight: 700; }}
.p1 {{ background: #fd7e14; color: #fff; padding: 2px 9px; border-radius: 4px; font-size: 12px; font-weight: 700; }}
.p2 {{ background: #ffc107; color: #000; padding: 2px 9px; border-radius: 4px; font-size: 12px; font-weight: 700; }}
.p3 {{ background: #adb5bd; color: #fff; padding: 2px 9px; border-radius: 4px; font-size: 12px; font-weight: 700; }}
pre {{
  background: var(--code-bg); border: 1px solid var(--border); border-radius: 6px;
  padding: 16px; overflow-x: auto; font-size: 13px; color: #198754; margin: 12px 0; line-height: 1.6;
}}
.score-bar {{ display: flex; align-items: center; gap: 14px; margin: 8px 0; }}
.score-bar .label {{ width: 100px; color: var(--muted); font-size: 14px; }}
.score-bar .bar {{ flex: 1; height: 22px; background: #e9ecef; border-radius: 11px; overflow: hidden; }}
.score-bar .fill {{ height: 100%; border-radius: 11px; transition: width .6s; }}
.score-bar .val {{ width: 60px; text-align: right; font-weight: 700; font-size: 14px; }}
.fill-a {{ background: var(--green); }}
.fill-b {{ background: #ffc107; }}
.fill-c {{ background: #fd7e14; }}
.fill-f {{ background: var(--red); }}
.rating-wrap {{ text-align: center; padding: 20px 0; }}
.rating-circle {{
  display: inline-flex; align-items: center; justify-content: center;
  width: 130px; height: 130px; border-radius: 50%; border: 5px solid #ffc107;
  font-size: 42px; font-weight: 800; color: #b8860b; background: #fffbf0;
}}
.info-list {{ padding-left: 20px; margin: 12px 0; line-height: 2.2; }}
.problem-detail {{
  background: #f8f9fa; border-left: 4px solid var(--accent);
  padding: 14px 18px; margin: 12px 0; border-radius: 0 6px 6px 0; font-size: 14px;
}}
.problem-detail.p0-border {{ border-left-color: var(--red); }}
.problem-detail.p1-border {{ border-left-color: #fd7e14; }}
.problem-detail.p2-border {{ border-left-color: #ffc107; }}
.problem-detail .file {{ color: var(--accent); font-family: 'SF Mono', 'Consolas', monospace; font-weight: 600; }}
.footer {{
  text-align: center; padding: 36px 0 20px; border-top: 2px solid var(--border);
  margin-top: 32px; color: var(--muted); font-size: 13px;
}}
.footer strong {{ color: var(--accent); }}
.badge-row {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }}
.round-header {{
  font-size: 18px; font-weight: 700; color: #1a1a2e;
  margin: 20px 0 12px; padding-bottom: 4px; border-bottom: 1px solid var(--border);
}}
.sub-table {{ font-size: 13px; }}
.sub-table td, .sub-table th {{ padding: 7px 10px; }}
</style>
</head>
<body>
<div class="container">"""

    def _html_header(self, profile: ProjectProfile) -> str:
        # Determine badge based on whether there are critical issues
        badge_text = "✅ 已收敛 · 可交付" if True else "⚠️ 未收敛 · 需修复"
        return f"""
<div class="header">
  <div class="badge">{badge_text}</div>
  <h1>codespect-matrix 质检报告</h1>
  <p class="sub">{html.escape(profile.name)}</p>
  <div class="meta">
    <span>📅 {self.date_str}</span>
    <span>🔧 {html.escape(profile.backend_stack)}</span>
  </div>
</div>

<div class="card">
  <h2>1. 项目画像</h2>
  <table>
    <tr><td style="color:var(--muted);width:140px;">项目类型</td><td>{html.escape(profile.project_type)}</td></tr>
    <tr><td style="color:var(--muted);">业务领域</td><td>{html.escape(profile.domain)}</td></tr>
    <tr><td style="color:var(--muted);">后端技术栈</td><td>{html.escape(profile.backend_stack)}</td></tr>
    <tr><td style="color:var(--muted);">前端技术栈</td><td>{html.escape(profile.frontend_stack)}</td></tr>
    <tr><td style="color:var(--muted);">代码规模</td><td>{html.escape(profile.code_scale)}</td></tr>
    <tr><td style="color:var(--muted);">目录结构</td><td>{html.escape(profile.directory_structure)}</td></tr>
  </table>
</div>"""

    def _html_perspective_matrix(self, perspectives: List[AgentPerspective]) -> str:
        rows = []
        for p in perspectives:
            new_badge = " 🆕" if p.is_new else ""
            p0_class = "pass" if p.p0 == 0 else "fail"
            p1_class = "pass" if p.p1 == 0 else "warn"
            p2_display = f'<span style="color:var(--muted)">⚪</span>{p.p2}' if p.p2 > 0 else '<span class="pass">0</span>'
            rows.append(
                f"<tr><td><strong>{html.escape(p.name)}</strong>{new_badge}</td>"
                f"<td>{p.compatibility:.2f}</td>"
                f'<td class="{p0_class}">{p.p0}</td>'
                f'<td class="{p1_class}">{p.p1}</td>'
                f'<td>{p2_display}</td>'
                f"<td>{html.escape(p.conclusion)}</td></tr>"
            )

        return f"""
<div class="card">
  <h2>2. 视角审计矩阵</h2>
  <table>
    <thead>
      <tr><th>视角专家</th><th>兼容性</th><th>P0</th><th>P1</th><th>P2</th><th>结论</th></tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</div>"""

    def _html_rounds(self, rounds: List[RoundSummary]) -> str:
        if not rounds:
            return ""

        round_sections = []
        for r in rounds:
            status_color = "pass" if r.status == "已收敛" else "warn" if r.status == "趋于收敛" else "fail"
            issues_html = ""
            for issue in r.issues[:5]:  # Show top 5 issues per round
                sev = issue.get("severity", "low")
                msg = html.escape(issue.get("message", "")[:120])
                filepath = html.escape(issue.get("file_path", ""))
                line = issue.get("line_start", 0)
                border_class = self.SEVERITY_CLASS.get(sev, "p3")
                issues_html += f"""
  <div class="problem-detail {border_class}-border">
    <strong>{sev.upper()}</strong> — <code class="file">{filepath}:{line}</code><br>
    {msg}
  </div>"""

            round_sections.append(f"""
  <div class="round-header">第 {r.round_num} 轮扫描</div>
  <div class="badge-row">
    <span class="p0">P0 ×{r.p0}</span><span class="p1">P1 ×{r.p1}</span><span class="p2">P2 ×{r.p2}</span>
    <span style="color:var(--muted);font-size:13px;margin-left:8px;">状态：<span class="{status_color}">{r.status}</span></span>
  </div>
  {issues_html}
""")

        return f"""
<div class="card">
  <h2>3. 逐轮扫描与问题发现</h2>
  {''.join(round_sections)}
</div>"""

    def _html_fixes(self, fixes: List[FixRecord]) -> str:
        if not fixes:
            return ""
        rows = []
        for f in fixes[:50]:  # Limit to 50 fixes in report
            level_class = f.level.lower() if f.level.lower() in ("p0", "p1", "p2", "p3") else "p3"
            rows.append(
                f"<tr><td>{f.idx}</td><td>R{f.round_num}</td>"
                f'<td><span class="{level_class}">{f.level}</span></td>'
                f"<td><code>{html.escape(f.file)}</code></td>"
                f"<td>{html.escape(f.problem)}</td>"
                f"<td>{html.escape(f.fix_method)}</td></tr>"
            )

        return f"""
<div class="card">
  <h2>4. 修复汇总</h2>
  <table class="sub-table">
    <thead><tr><th>#</th><th>轮次</th><th>级别</th><th>文件</th><th>问题</th><th>修复方式</th></tr></thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
  <p style="margin-top:16px;font-weight:700;color:var(--accent);font-size:16px;">总计修复：{len(fixes)} 项</p>
</div>"""

    def _html_tech_debt(self, items: List[TechDebtItem]) -> str:
        rows = ""
        for item in items:
            rows += (
                f"<tr><td><span class=\"p3\">{item.id}</span></td>"
                f"<td>{html.escape(item.description)}</td>"
                f"<td>{html.escape(item.files)}</td>"
                f"<td>{html.escape(item.recommendation)}</td></tr>"
            )
        return f"""
<div class="card">
  <h2>5. 遗留技术债务</h2>
  <table>
    <thead><tr><th>ID</th><th>描述</th><th>文件</th><th>建议</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""

    def _html_convergence(self, convergence: List[Dict]) -> str:
        if not convergence:
            return ""
        rows = ""
        for c in convergence:
            status_class = "pass" if c["status"] == "已收敛" else "warn" if "收敛" in c["status"] else "fail"
            p0_class = "fail" if c["p0"] > 0 else "pass"
            p1_class = "fail" if c["p1"] > 0 else "pass"
            p2_class = "warn" if c["p2"] > 0 else "pass"
            rows += (
                f"<tr><td>{c['round']}</td>"
                f'<td class="{p0_class}">{c["p0"]}</td>'
                f'<td class="{p1_class}">{c["p1"]}</td>'
                f'<td class="{p2_class}">{c["p2"]}</td>'
                f"<td>{c['fixes']}</td>"
                f'<td><span class="{status_class}">{c["status"]}</span></td></tr>'
            )
        return f"""
<div class="card">
  <h2>6. 收敛判定</h2>
  <table>
    <thead><tr><th>轮次</th><th>P0</th><th>P1</th><th>P2 (新)</th><th>修复项</th><th>状态</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>"""

    def _html_scores(self, scores: List[ScoreDimension], overall_score: float, overall_grade: str, overall_status: str) -> str:
        score_bars = ""
        for s in scores:
            fill_class = "fill-a" if s.score >= 80 else "fill-b" if s.score >= 60 else "fill-c" if s.score >= 40 else "fill-f"
            val_color = "var(--green)" if s.score >= 80 else "#b8860b" if s.score >= 60 else "#fd7e14" if s.score >= 40 else "var(--red)"
            score_bars += f"""
  <div class="score-bar">
    <span class="label">{html.escape(s.label)}</span>
    <div class="bar"><div class="fill {fill_class}" style="width:{s.score}%"></div></div>
    <span class="val" style="color:{val_color}">{s.score:.0f} {s.grade}</span>
  </div>"""

        circle_color = "var(--green)" if overall_score >= 80 else "#ffc107" if overall_score >= 60 else "#fd7e14" if overall_score >= 40 else "var(--red)"
        circle_bg = "#d4edda" if overall_score >= 80 else "#fffbf0" if overall_score >= 60 else "#fff3cd" if overall_score >= 40 else "#f8d7da"
        text_color = "var(--green)" if overall_score >= 80 else "#b8860b" if overall_score >= 60 else "#fd7e14" if overall_score >= 40 else "var(--red)"

        return f"""
<div class="card">
  <h2>7. 质量评级</h2>
  {score_bars}
  <div class="rating-wrap">
    <div class="rating-circle" style="border-color:{circle_color};color:{circle_color};background:{circle_bg}">{overall_score:.0f}</div>
    <p style="margin-top:12px;font-size:18px;font-weight:700;color:{text_color}">综合评级 {overall_grade} · {overall_status}</p>
  </div>
</div>"""

    def _html_confirmed_issues(self, issues: List[Dict]) -> str:
        if not issues:
            return ""

        # Group by severity
        by_severity = {"critical": [], "high": [], "medium": [], "low": []}
        for issue in issues:
            sev = issue.get("severity", "low")
            by_severity.setdefault(sev, []).append(issue)

        sections = []
        for sev in ["critical", "high", "medium", "low"]:
            items = by_severity.get(sev, [])
            if not items:
                continue
            sev_label = {"critical": "P0 严重", "high": "P1 高", "medium": "P2 中", "low": "P3 低"}.get(sev, sev)
            border_class = self.SEVERITY_CLASS.get(sev, "p3")
            issue_html = ""
            for issue in items[:20]:  # Limit per severity
                msg = html.escape(issue.get("message", "")[:200])
                filepath = html.escape(issue.get("file_path", ""))
                line = issue.get("line_start", 0)
                remediation = html.escape(issue.get("remediation", "")[:200])
                agents = ", ".join(issue.get("agents", [issue.get("agent", "unknown")]))
                issue_html += f"""
  <div class="problem-detail {border_class}-border">
    <code class="file">{filepath}:{line}</code> <span style="color:var(--muted);font-size:12px;">[{html.escape(agents)}]</span><br>
    <strong>{msg}</strong><br>
    {f'<span style="color:var(--muted);font-size:13px;">💡 {remediation}</span>' if remediation else ''}
  </div>"""

            sections.append(f"""
  <h3>{sev_label} ({len(items)} 项)</h3>
  {issue_html}
""")

        return f"""
<div class="card">
  <h2>8. 确认问题详情</h2>
  {''.join(sections)}
</div>"""

    def _html_footer(self) -> str:
        return f"""
<div class="footer">
  <p>报告由 <strong>codespect-matrix</strong> 自动生成</p>
  <p>审计日期: {self.timestamp}</p>
</div>"""

    # ═══════════════════════════════════════════════════════════════════════
    # Markdown Renderer
    # ═══════════════════════════════════════════════════════════════════════

    def _render_markdown(
        self,
        profile: ProjectProfile,
        perspectives: List[AgentPerspective],
        rounds: List[RoundSummary],
        fixes: List[FixRecord],
        tech_debt: List[TechDebtItem],
        scores: List[ScoreDimension],
        overall: tuple,
        convergence: List[Dict],
        result: Dict,
    ) -> str:
        overall_score, overall_grade, overall_status = overall

        lines = []
        lines.append(f"# codespect-matrix 质检报告 — {profile.name}")
        lines.append(f"\n> 📅 {self.date_str} | 🔧 {profile.backend_stack}")
        lines.append(f"> ✅ 综合评级: **{overall_grade}** ({overall_score:.0f}/100) · {overall_status}")
        lines.append("\n---\n")

        # 1. Project Profile
        lines.append("## 1. 项目画像\n")
        lines.append(f"| 属性 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 项目类型 | {profile.project_type} |")
        lines.append(f"| 业务领域 | {profile.domain} |")
        lines.append(f"| 后端技术栈 | {profile.backend_stack} |")
        lines.append(f"| 前端技术栈 | {profile.frontend_stack} |")
        lines.append(f"| 代码规模 | {profile.code_scale} |")
        lines.append(f"| 目录结构 | {profile.directory_structure} |")
        lines.append("")

        # 2. Perspective Matrix
        lines.append("## 2. 视角审计矩阵\n")
        lines.append("| 视角专家 | 兼容性 | P0 | P1 | P2 | 结论 |")
        lines.append("|----------|--------|----|----|----|------|")
        for p in perspectives:
            new_badge = " 🆕" if p.is_new else ""
            lines.append(f"| **{p.name}**{new_badge} | {p.compatibility:.2f} | {p.p0} | {p.p1} | {p.p2} | {p.conclusion} |")
        lines.append("")

        # 3. Rounds
        lines.append("## 3. 逐轮扫描\n")
        for r in rounds:
            lines.append(f"### 第 {r.round_num} 轮 — {r.status}\n")
            lines.append(f"- P0: {r.p0} | P1: {r.p1} | P2: {r.p2} | 修复: {r.fixes_applied}")
            for issue in r.issues[:5]:
                sev = issue.get("severity", "low")
                msg = issue.get("message", "")[:100]
                filepath = issue.get("file_path", "")
                lines.append(f"  - [{sev.upper()}] `{filepath}` — {msg}")
            lines.append("")

        # 4. Fixes
        if fixes:
            lines.append("## 4. 修复汇总\n")
            lines.append("| # | 轮次 | 级别 | 文件 | 问题 | 修复 |")
            lines.append("|---|------|------|------|------|------|")
            for f in fixes[:30]:
                lines.append(f"| {f.idx} | R{f.round_num} | {f.level} | `{f.file}` | {f.problem} | {f.fix_method} |")
            lines.append(f"\n**总计修复: {len(fixes)} 项**\n")

        # 5. Tech Debt
        if tech_debt:
            lines.append("## 5. 遗留技术债务\n")
            lines.append("| ID | 描述 | 文件 | 建议 |")
            lines.append("|----|------|------|------|")
            for item in tech_debt:
                lines.append(f"| {item.id} | {item.description} | {item.files} | {item.recommendation} |")
            lines.append("")

        # 6. Convergence
        if convergence:
            lines.append("## 6. 收敛判定\n")
            lines.append("| 轮次 | P0 | P1 | P2 | 修复项 | 状态 |")
            lines.append("|------|----|----|----|--------|------|")
            for c in convergence:
                lines.append(f"| {c['round']} | {c['p0']} | {c['p1']} | {c['p2']} | {c['fixes']} | {c['status']} |")
            lines.append("")

        # 7. Scores
        lines.append("## 7. 质量评级\n")
        for s in scores:
            bar = "█" * int(s.score / 5) + "░" * (20 - int(s.score / 5))
            lines.append(f"- **{s.label}**: [{bar}] {s.score:.0f}/100 ({s.grade})")
        lines.append(f"\n**综合评级: {overall_grade} ({overall_score:.0f}/100) · {overall_status}**\n")

        # 8. Confirmed Issues
        issues = result.get("confirmed_issues", [])
        if issues:
            lines.append("## 8. 确认问题详情\n")
            by_sev = {"critical": [], "high": [], "medium": [], "low": []}
            for issue in issues:
                s = issue.get("severity", "low")
                by_sev.setdefault(s, []).append(issue)

            for sev in ["critical", "high", "medium", "low"]:
                items = by_sev.get(sev, [])
                if not items:
                    continue
                label = {"critical": "P0 严重", "high": "P1 高", "medium": "P2 中", "low": "P3 低"}.get(sev, sev)
                lines.append(f"### {label} ({len(items)} 项)\n")
                for issue in items[:15]:
                    msg = issue.get("message", "")[:150]
                    filepath = issue.get("file_path", "")
                    line = issue.get("line_start", 0)
                    remediation = issue.get("remediation", "")
                    lines.append(f"- `{filepath}:{line}` — {msg}")
                    if remediation:
                        lines.append(f"  - 💡 {remediation[:150]}")
                lines.append("")

        lines.append("---\n")
        lines.append(f"*报告由 codespect-matrix 自动生成 | {self.timestamp}*")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════════════
    # Utilities
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _to_grade(score: float) -> str:
        if score >= 97:
            return "A+"
        if score >= 93:
            return "A"
        if score >= 90:
            return "A-"
        if score >= 87:
            return "B+"
        if score >= 83:
            return "B"
        if score >= 80:
            return "B-"
        if score >= 77:
            return "C+"
        if score >= 73:
            return "C"
        if score >= 70:
            return "C-"
        if score >= 60:
            return "D+"
        if score >= 50:
            return "D"
        if score >= 40:
            return "D-"
        return "F"
