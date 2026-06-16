"""Comprehensive report generator — HTML + Markdown dual format.

Report structure (round-centric):
  1. Project Profile
  2. Round Reports (repeat per round)
     2.1 Five-Phase Scan
     2.2 Issue Discovery & Remediation
     2.3 Remaining P3 Technical Debt
     2.4 Convergence Determination
     2.5 Quality Rating
     2.6 Round Conclusion
  3. All Fixes Summary
  4. Final Convergence & Conclusion
"""

from __future__ import annotations

import html
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


# ─── Data Structures ─────────────────────────────────────────────────────────

@dataclass
class ScanPhase:
    name: str
    status: str          # pass / warn / fail / info
    details: str = ""


@dataclass
class IssueItem:
    severity: str        # critical / high / medium / low
    check_name: str
    message: str
    file_path: str
    line_start: int
    remediation: str = ""
    evidence: str = ""


@dataclass
class FixItem:
    idx: int
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


@dataclass
class ScoreDimension:
    label: str
    score: float         # 0-100
    grade: str


@dataclass
class RoundReport:
    round_num: int
    scan_phases: List[ScanPhase] = field(default_factory=list)
    issues_found: List[IssueItem] = field(default_factory=list)
    fixes_applied: List[FixItem] = field(default_factory=list)
    tech_debt: List[TechDebtItem] = field(default_factory=list)
    convergence_status: str = "未收敛"   # 未收敛 / 趋于收敛 / 已收敛
    scores: List[ScoreDimension] = field(default_factory=list)
    conclusion: str = ""


@dataclass
class ProjectProfile:
    name: str
    project_type: str
    domain: str
    backend_stack: str
    frontend_stack: str
    code_scale: str
    directory_structure: str


# ─── Report Generator ────────────────────────────────────────────────────────

class ComprehensiveReportGenerator:
    """Generate round-centric HTML/Markdown audit reports."""

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
        rounds: List[RoundReport],
        profile: Optional[Dict] = None,
        format: str = "html",
    ) -> str:
        """Generate report in specified format.

        Args:
            rounds: list of RoundReport, one per review cycle
            profile: project profile dict from scanner
            format: "html" | "md" | "markdown"
        """
        project_profile = self._build_project_profile(profile)
        all_fixes = self._collect_all_fixes(rounds)
        final_scores, final_grade, final_status = self._compute_final(rounds)

        if format.lower() == "html":
            return self._render_html(
                project_profile, rounds, all_fixes,
                final_scores, final_grade, final_status,
            )
        else:
            return self._render_markdown(
                project_profile, rounds, all_fixes,
                final_scores, final_grade, final_status,
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
            code_scale=scale_str,
            directory_structure=p.get("directory_structure", "Standard layout"),
        )

    def _collect_all_fixes(self, rounds: List[RoundReport]) -> List[FixItem]:
        fixes = []
        idx = 1
        for r in rounds:
            for f in r.fixes_applied:
                f.idx = idx
                fixes.append(f)
                idx += 1
        return fixes

    def _compute_final(self, rounds: List[RoundReport]) -> tuple:
        if not rounds:
            return [], "F", "需立即修复"
        last = rounds[-1]
        scores = last.scores
        if not scores:
            return [], "F", "需立即修复"
        avg = sum(s.score for s in scores) / len(scores)
        grade = self._to_grade(avg)
        status = "可交付" if avg >= 70 and last.convergence_status == "已收敛" else "需整改" if avg >= 50 else "需立即修复"
        return scores, grade, status

    # ═══════════════════════════════════════════════════════════════════════
    # HTML Renderer
    # ═══════════════════════════════════════════════════════════════════════

    def _render_html(
        self,
        profile: ProjectProfile,
        rounds: List[RoundReport],
        all_fixes: List[FixItem],
        final_scores: List[ScoreDimension],
        final_grade: str,
        final_status: str,
    ) -> str:
        parts = []
        parts.append(self._html_head(profile.name))
        parts.append(self._html_header(profile, final_grade, final_status))

        # Section 2: Round Reports
        for r in rounds:
            parts.append(self._html_round(r))

        # Section 3: All Fixes Summary
        if all_fixes:
            parts.append(self._html_all_fixes(all_fixes))

        # Section 4: Final Convergence
        parts.append(self._html_final_convergence(rounds, final_scores, final_grade, final_status))

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
  --blue-bg: #cfe2ff; --blue: #084298;
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
.header .badge.warn {{ background: var(--yellow-bg); color: var(--yellow); border-color: #ffecb5; }}
.header .badge.fail {{ background: var(--red-bg); color: var(--red); border-color: #f5c2c7; }}
.header .sub {{ color: var(--muted); font-size: 14px; margin-top: 2px; }}
.header .meta {{ color: var(--muted); font-size: 13px; margin-top: 8px; }}
.card {{
  background: var(--card); border: 1px solid var(--border); border-radius: 10px;
  padding: 28px; margin-bottom: 24px; box-shadow: var(--shadow);
}}
h2 {{
  font-size: 21px; margin-bottom: 18px; padding-bottom: 8px;
  border-bottom: 2px solid var(--accent); color: #1a1a2e;
}}
h3 {{ font-size: 17px; margin: 24px 0 10px; color: var(--accent); }}
h4 {{ font-size: 15px; margin: 16px 0 6px; color: #343a40; }}
table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 14px; }}
th, td {{ text-align: left; padding: 8px 12px; border: 1px solid var(--border); }}
th {{ background: #e9ecef; font-weight: 600; color: #495057; font-size: 13px; }}
tr:nth-child(even) td {{ background: var(--table-stripe); }}
.pass {{ color: var(--green); font-weight: 600; }}
.warn {{ color: var(--yellow); }}
.fail {{ color: var(--red); font-weight: 600; }}
.p0 {{ background: var(--red); color: #fff; padding: 2px 9px; border-radius: 4px; font-size: 12px; font-weight: 700; }}
.p1 {{ background: #fd7e14; color: #fff; padding: 2px 9px; border-radius: 4px; font-size: 12px; font-weight: 700; }}
.p2 {{ background: #ffc107; color: #000; padding: 2px 9px; border-radius: 4px; font-size: 12px; font-weight: 700; }}
.p3 {{ background: #adb5bd; color: #fff; padding: 2px 9px; border-radius: 4px; font-size: 12px; font-weight: 700; }}
.phase-pass {{ color: var(--green); font-weight: 700; }}
.phase-warn {{ color: var(--yellow); font-weight: 700; }}
.phase-fail {{ color: var(--red); font-weight: 700; }}
.phase-info {{ color: var(--accent); font-weight: 700; }}
pre {{
  background: var(--code-bg); border: 1px solid var(--border); border-radius: 6px;
  padding: 14px; overflow-x: auto; font-size: 13px; color: #198754; margin: 10px 0; line-height: 1.6;
}}
.score-bar {{ display: flex; align-items: center; gap: 14px; margin: 6px 0; }}
.score-bar .label {{ width: 100px; color: var(--muted); font-size: 14px; }}
.score-bar .bar {{ flex: 1; height: 20px; background: #e9ecef; border-radius: 10px; overflow: hidden; }}
.score-bar .fill {{ height: 100%; border-radius: 10px; transition: width .6s; }}
.score-bar .val {{ width: 60px; text-align: right; font-weight: 700; font-size: 14px; }}
.fill-a {{ background: var(--green); }}
.fill-b {{ background: #ffc107; }}
.fill-c {{ background: #fd7e14; }}
.fill-f {{ background: var(--red); }}
.rating-wrap {{ text-align: center; padding: 16px 0; }}
.rating-circle {{
  display: inline-flex; align-items: center; justify-content: center;
  width: 120px; height: 120px; border-radius: 50%; border: 4px solid #ffc107;
  font-size: 38px; font-weight: 800; color: #b8860b; background: #fffbf0;
}}
.problem-detail {{
  background: #f8f9fa; border-left: 4px solid var(--accent);
  padding: 12px 16px; margin: 10px 0; border-radius: 0 6px 6px 0; font-size: 14px;
}}
.problem-detail.p0-border {{ border-left-color: var(--red); }}
.problem-detail.p1-border {{ border-left-color: #fd7e14; }}
.problem-detail.p2-border {{ border-left-color: #ffc107; }}
.problem-detail .file {{ color: var(--accent); font-family: 'SF Mono', 'Consolas', monospace; font-weight: 600; font-size: 12px; }}
.round-card {{ border-left: 4px solid var(--accent); }}
.round-card.converged {{ border-left-color: var(--green); }}
.round-card.partial {{ border-left-color: #ffc107; }}
.footer {{
  text-align: center; padding: 32px 0 20px; border-top: 2px solid var(--border);
  margin-top: 28px; color: var(--muted); font-size: 13px;
}}
.footer strong {{ color: var(--accent); }}
.badge-row {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }}
.sub-table {{ font-size: 13px; }}
.sub-table td, .sub-table th {{ padding: 6px 10px; }}
.conclusion-box {{
  background: var(--blue-bg); border: 1px solid #b6d4fe; border-radius: 6px;
  padding: 14px 18px; margin: 12px 0; color: var(--blue); font-size: 14px;
}}
.conclusion-box.success {{ background: var(--green-bg); border-color: #badbcc; color: var(--green); }}
.conclusion-box.warning {{ background: var(--yellow-bg); border-color: #ffecb5; color: var(--yellow); }}
</style>
</head>
<body>
<div class="container">"""

    def _html_header(self, profile: ProjectProfile, final_grade: str, final_status: str) -> str:
        badge_class = "pass" if final_status == "可交付" else "warn" if final_status == "需整改" else "fail"
        badge_text = f"✅ {final_status}" if final_status == "可交付" else f"⚠️ {final_status}"
        return f"""
<div class="header">
  <div class="badge {badge_class}">{badge_text}</div>
  <h1>codespect-matrix 质检报告</h1>
  <p class="sub">{html.escape(profile.name)}</p>
  <div class="meta">
    <span>📅 {self.date_str}</span>
    <span>🔧 {html.escape(profile.backend_stack)}</span>
    <span>📊 综合评级 {final_grade}</span>
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

    def _html_round(self, r: RoundReport) -> str:
        border_class = "converged" if r.convergence_status == "已收敛" else "partial" if "收敛" in r.convergence_status else ""
        status_badge = f'<span class="p0">未收敛</span>' if r.convergence_status == "未收敛" else f'<span class="p2">趋于收敛</span>' if "趋于" in r.convergence_status else f'<span class="pass" style="background:var(--green);color:#fff;padding:2px 10px;border-radius:4px;font-size:12px;font-weight:700;">已收敛</span>'

        # 2.1 Five-phase scan
        phases_html = ""
        for phase in r.scan_phases:
            status_class = f"phase-{phase.status}"
            phases_html += f"<tr><td>{html.escape(phase.name)}</td><td class='{status_class}'>{html.escape(phase.status.upper())}</td><td>{html.escape(phase.details)}</td></tr>"

        # 2.2 Issues found
        issues_html = ""
        by_sev = {"critical": [], "high": [], "medium": [], "low": []}
        for issue in r.issues_found:
            by_sev.setdefault(issue.severity, []).append(issue)
        for sev in ["critical", "high", "medium", "low"]:
            items = by_sev.get(sev, [])
            if not items:
                continue
            label = {"critical": "P0 严重", "high": "P1 高", "medium": "P2 中", "low": "P3 低"}.get(sev, sev)
            border = self.SEVERITY_CLASS.get(sev, "p3")
            issues_html += f"<h4>{label} ({len(items)} 项)</h4>"
            for issue in items:
                issues_html += f"""
  <div class="problem-detail {border}-border">
    <span class="file">{html.escape(issue.file_path)}:{issue.line_start}</span><br>
    <strong>[{html.escape(issue.check_name)}]</strong> {html.escape(issue.message)}<br>
    {f'<span style="color:var(--muted);font-size:13px;">💡 {html.escape(issue.remediation)}</span>' if issue.remediation else ''}
  </div>"""

        # 2.3 Fixes applied
        fixes_html = ""
        if r.fixes_applied:
            fixes_html += '<table class="sub-table"><thead><tr><th>#</th><th>级别</th><th>文件</th><th>问题</th><th>修复方式</th></tr></thead><tbody>'
            for f in r.fixes_applied:
                level_class = f.level.lower() if f.level.lower() in ("p0", "p1", "p2", "p3") else "p3"
                fixes_html += f'<tr><td>{f.idx}</td><td><span class="{level_class}">{f.level}</span></td><td><code>{html.escape(f.file)}</code></td><td>{html.escape(f.problem)}</td><td>{html.escape(f.fix_method)}</td></tr>'
            fixes_html += f'</tbody></table><p style="margin-top:8px;font-weight:600;color:var(--accent);">本轮修复: {len(r.fixes_applied)} 项</p>'
        else:
            fixes_html = '<p style="color:var(--muted);font-size:13px;">本轮未产生自动修复</p>'

        # 2.4 Tech debt
        debt_html = ""
        if r.tech_debt:
            debt_html += '<table class="sub-table"><thead><tr><th>ID</th><th>描述</th><th>文件</th><th>建议</th></tr></thead><tbody>'
            for d in r.tech_debt:
                debt_html += f'<tr><td><span class="p3">{d.id}</span></td><td>{html.escape(d.description)}</td><td>{html.escape(d.files)}</td><td>{html.escape(d.recommendation)}</td></tr>'
            debt_html += '</tbody></table>'
        else:
            debt_html = '<p style="color:var(--muted);font-size:13px;">本轮无遗留技术债务</p>'

        # 2.5 Scores
        scores_html = ""
        for s in r.scores:
            fill_class = "fill-a" if s.score >= 80 else "fill-b" if s.score >= 60 else "fill-c" if s.score >= 40 else "fill-f"
            val_color = "var(--green)" if s.score >= 80 else "#b8860b" if s.score >= 60 else "#fd7e14" if s.score >= 40 else "var(--red)"
            scores_html += f"""
  <div class="score-bar">
    <span class="label">{html.escape(s.label)}</span>
    <div class="bar"><div class="fill {fill_class}" style="width:{s.score}%"></div></div>
    <span class="val" style="color:{val_color}">{s.score:.0f} {s.grade}</span>
  </div>"""

        # 2.6 Conclusion
        conclusion_class = "success" if r.convergence_status == "已收敛" else "warning"
        return f"""
<div class="card round-card {border_class}">
  <h2>2.{r.round_num} 第 {r.round_num} 轮审查</h2>
  <div class="badge-row">
    {status_badge}
    <span style="color:var(--muted);font-size:13px;">P0:{len(by_sev.get('critical',[]))} P1:{len(by_sev.get('high',[]))} P2:{len(by_sev.get('medium',[]))}</span>
  </div>

  <h3>2.{r.round_num}.1 五阶段扫描</h3>
  <table class="sub-table">
    <thead><tr><th>阶段</th><th>状态</th><th>说明</th></tr></thead>
    <tbody>{phases_html}</tbody>
  </table>

  <h3>2.{r.round_num}.2 问题发现与修复</h3>
  {issues_html}
  {fixes_html}

  <h3>2.{r.round_num}.3 遗留技术债务</h3>
  {debt_html}

  <h3>2.{r.round_num}.4 收敛判定</h3>
  <p><strong>状态:</strong> {r.convergence_status}</p>

  <h3>2.{r.round_num}.5 质量评级</h3>
  {scores_html}

  <h3>2.{r.round_num}.6 本轮结论</h3>
  <div class="conclusion-box {conclusion_class}">
    {html.escape(r.conclusion) if r.conclusion else '本轮审查完成，问题已记录。'}
  </div>
</div>"""

    def _html_all_fixes(self, fixes: List[FixItem]) -> str:
        rows = ""
        for f in fixes:
            level_class = f.level.lower() if f.level.lower() in ("p0", "p1", "p2", "p3") else "p3"
            rows += f'<tr><td>{f.idx}</td><td>R{f.round_num if hasattr(f, "round_num") else "?"}</td><td><span class="{level_class}">{f.level}</span></td><td><code>{html.escape(f.file)}</code></td><td>{html.escape(f.problem)}</td><td>{html.escape(f.fix_method)}</td></tr>'
        return f"""
<div class="card">
  <h2>3. 全部修复汇总</h2>
  <table class="sub-table">
    <thead><tr><th>#</th><th>轮次</th><th>级别</th><th>文件</th><th>问题</th><th>修复方式</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <p style="margin-top:16px;font-weight:700;color:var(--accent);font-size:16px;">总计修复: {len(fixes)} 项</p>
</div>"""

    def _html_final_convergence(
        self, rounds: List[RoundReport],
        final_scores: List[ScoreDimension], final_grade: str, final_status: str
    ) -> str:
        rows = ""
        for r in rounds:
            p0 = len([i for i in r.issues_found if i.severity == "critical"])
            p1 = len([i for i in r.issues_found if i.severity == "high"])
            p2 = len([i for i in r.issues_found if i.severity == "medium"])
            p0_class = "fail" if p0 > 0 else "pass"
            p1_class = "fail" if p1 > 0 else "pass"
            p2_class = "warn" if p2 > 0 else "pass"
            status_class = "pass" if r.convergence_status == "已收敛" else "warn" if "收敛" in r.convergence_status else "fail"
            rows += f'<tr><td>第 {r.round_num} 轮</td><td class="{p0_class}">{p0}</td><td class="{p1_class}">{p1}</td><td class="{p2_class}">{p2}</td><td>{len(r.fixes_applied)}</td><td><span class="{status_class}">{r.convergence_status}</span></td></tr>'

        scores_html = ""
        for s in final_scores:
            fill_class = "fill-a" if s.score >= 80 else "fill-b" if s.score >= 60 else "fill-c" if s.score >= 40 else "fill-f"
            val_color = "var(--green)" if s.score >= 80 else "#b8860b" if s.score >= 60 else "#fd7e14" if s.score >= 40 else "var(--red)"
            scores_html += f"""
  <div class="score-bar">
    <span class="label">{html.escape(s.label)}</span>
    <div class="bar"><div class="fill {fill_class}" style="width:{s.score}%"></div></div>
    <span class="val" style="color:{val_color}">{s.score:.0f} {s.grade}</span>
  </div>"""

        circle_color = "var(--green)" if final_status == "可交付" else "#ffc107" if final_status == "需整改" else "var(--red)"
        circle_bg = "#d4edda" if final_status == "可交付" else "#fff3cd" if final_status == "需整改" else "#f8d7da"
        text_color = "var(--green)" if final_status == "可交付" else "#b8860b" if final_status == "需整改" else "var(--red)"

        conclusion_box_class = "success" if final_status == "可交付" else "warning"
        conclusion_text = "项目已通过多轮审查收敛，质量评级达标，可进入交付流程。" if final_status == "可交付" else "项目仍存在未收敛问题，建议继续修复后再评估。"

        return f"""
<div class="card">
  <h2>4. 最终收敛判断与结论</h2>

  <h3>4.1 轮次收敛对比</h3>
  <table>
    <thead><tr><th>轮次</th><th>P0</th><th>P1</th><th>P2</th><th>修复项</th><th>状态</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>

  <h3>4.2 最终质量评级</h3>
  {scores_html}
  <div class="rating-wrap">
    <div class="rating-circle" style="border-color:{circle_color};color:{circle_color};background:{circle_bg}">{sum(s.score for s in final_scores)//len(final_scores) if final_scores else 0}</div>
    <p style="margin-top:12px;font-size:18px;font-weight:700;color:{text_color}">综合评级 {final_grade} · {final_status}</p>
  </div>

  <h3>4.3 总体结论</h3>
  <div class="conclusion-box {conclusion_box_class}">
    {conclusion_text}
  </div>
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
        rounds: List[RoundReport],
        all_fixes: List[FixItem],
        final_scores: List[ScoreDimension], final_grade: str, final_status: str,
    ) -> str:
        lines = []
        lines.append(f"# codespect-matrix 质检报告 — {profile.name}")
        lines.append(f"\n> 📅 {self.date_str} | 🔧 {profile.backend_stack} | 📊 综合评级 {final_grade} · {final_status}")
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

        # 2. Round Reports
        for r in rounds:
            lines.append(f"## 2.{r.round_num} 第 {r.round_num} 轮审查 — {r.convergence_status}\n")

            # 2.1 Five-phase scan
            lines.append(f"### 2.{r.round_num}.1 五阶段扫描\n")
            lines.append("| 阶段 | 状态 | 说明 |")
            lines.append("|------|------|------|")
            for phase in r.scan_phases:
                status_emoji = {"pass": "✅", "warn": "⚠️", "fail": "❌", "info": "ℹ️"}.get(phase.status, "•")
                lines.append(f"| {phase.name} | {status_emoji} {phase.status.upper()} | {phase.details} |")
            lines.append("")

            # 2.2 Issues
            lines.append(f"### 2.{r.round_num}.2 问题发现与修复\n")
            by_sev = {"critical": [], "high": [], "medium": [], "low": []}
            for issue in r.issues_found:
                by_sev.setdefault(issue.severity, []).append(issue)
            for sev in ["critical", "high", "medium", "low"]:
                items = by_sev.get(sev, [])
                if not items:
                    continue
                label = {"critical": "P0 严重", "high": "P1 高", "medium": "P2 中", "low": "P3 低"}.get(sev, sev)
                lines.append(f"#### {label} ({len(items)} 项)")
                for issue in items:
                    lines.append(f"- `{issue.file_path}:{issue.line_start}` **[{issue.check_name}]** {issue.message}")
                    if issue.remediation:
                        lines.append(f"  - 💡 {issue.remediation}")
                lines.append("")

            if r.fixes_applied:
                lines.append(f"**本轮修复: {len(r.fixes_applied)} 项**\n")
                lines.append("| # | 级别 | 文件 | 问题 | 修复 |")
                lines.append("|---|------|------|------|------|")
                for f in r.fixes_applied:
                    lines.append(f"| {f.idx} | {f.level} | `{f.file}` | {f.problem} | {f.fix_method} |")
                lines.append("")

            # 2.3 Tech debt
            lines.append(f"### 2.{r.round_num}.3 遗留技术债务\n")
            if r.tech_debt:
                lines.append("| ID | 描述 | 文件 | 建议 |")
                lines.append("|----|------|------|------|")
                for d in r.tech_debt:
                    lines.append(f"| {d.id} | {d.description} | {d.files} | {d.recommendation} |")
            else:
                lines.append("本轮无遗留技术债务。")
            lines.append("")

            # 2.4 Convergence
            lines.append(f"### 2.{r.round_num}.4 收敛判定\n")
            lines.append(f"**状态: {r.convergence_status}**\n")

            # 2.5 Scores
            lines.append(f"### 2.{r.round_num}.5 质量评级\n")
            for s in r.scores:
                bar = "█" * int(s.score / 5) + "░" * (20 - int(s.score / 5))
                lines.append(f"- **{s.label}**: [{bar}] {s.score:.0f}/100 ({s.grade})")
            lines.append("")

            # 2.6 Conclusion
            lines.append(f"### 2.{r.round_num}.6 本轮结论\n")
            lines.append(f"> {r.conclusion if r.conclusion else '本轮审查完成，问题已记录。'}\n")

        # 3. All Fixes Summary
        if all_fixes:
            lines.append("## 3. 全部修复汇总\n")
            lines.append("| # | 级别 | 文件 | 问题 | 修复 |")
            lines.append("|---|------|------|------|------|")
            for f in all_fixes:
                lines.append(f"| {f.idx} | {f.level} | `{f.file}` | {f.problem} | {f.fix_method} |")
            lines.append(f"\n**总计修复: {len(all_fixes)} 项**\n")

        # 4. Final Convergence
        lines.append("## 4. 最终收敛判断与结论\n")
        lines.append("### 4.1 轮次收敛对比\n")
        lines.append("| 轮次 | P0 | P1 | P2 | 修复项 | 状态 |")
        lines.append("|------|----|----|----|--------|------|")
        for r in rounds:
            p0 = len([i for i in r.issues_found if i.severity == "critical"])
            p1 = len([i for i in r.issues_found if i.severity == "high"])
            p2 = len([i for i in r.issues_found if i.severity == "medium"])
            lines.append(f"| 第 {r.round_num} 轮 | {p0} | {p1} | {p2} | {len(r.fixes_applied)} | {r.convergence_status} |")
        lines.append("")

        lines.append("### 4.2 最终质量评级\n")
        for s in final_scores:
            bar = "█" * int(s.score / 5) + "░" * (20 - int(s.score / 5))
            lines.append(f"- **{s.label}**: [{bar}] {s.score:.0f}/100 ({s.grade})")
        lines.append(f"\n**综合评级: {final_grade} · {final_status}**\n")

        lines.append("### 4.3 总体结论\n")
        conclusion_text = "项目已通过多轮审查收敛，质量评级达标，可进入交付流程。" if final_status == "可交付" else "项目仍存在未收敛问题，建议继续修复后再评估。"
        lines.append(f"> {conclusion_text}\n")

        lines.append("---\n")
        lines.append(f"*报告由 codespect-matrix 自动生成 | {self.timestamp}*")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════════════
    # Utilities
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _to_grade(score: float) -> str:
        if score >= 97: return "A+"
        if score >= 93: return "A"
        if score >= 90: return "A-"
        if score >= 87: return "B+"
        if score >= 83: return "B"
        if score >= 80: return "B-"
        if score >= 77: return "C+"
        if score >= 73: return "C"
        if score >= 70: return "C-"
        if score >= 60: return "D+"
        if score >= 50: return "D"
        if score >= 40: return "D-"
        return "F"
