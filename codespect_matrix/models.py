"""数据模型 - 定义项目特征和验证结果的数据结构"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime, UTC
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """验证结果"""
    check_name: str
    status: str  # passed, failed, warning, info
    message: str
    severity: str  # critical, high, medium, low
    remediation: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status,
            "message": self.message,
            "severity": self.severity,
            "remediation": self.remediation,
        }


@dataclass
class RoundResult:
    """单轮校验结果"""
    round_number: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    issues_found: List[ValidationResult] = field(default_factory=list)
    issues_fixed: int = 0
    status: str = "pending"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_number": self.round_number,
            "timestamp": self.timestamp.isoformat(),
            "issues_found": [r.to_dict() for r in self.issues_found],
            "issues_fixed": self.issues_fixed,
            "status": self.status,
        }


@dataclass
class FixAction:
    """单条修复动作 — 精确到文件+行号+代码替换"""
    issue_check: str       # 来源检查项名称
    issue_message: str     # 来源问题描述
    severity: str          # 严重度
    file_path: str         # 相对于项目根目录的文件路径
    line_start: int        # 起始行号 (1-based)
    line_end: int          # 结束行号
    old_code: str          # 要被替换的原代码片段
    new_code: str          # 替换后的新代码片段
    description: str       # 人类可读的修复说明
    auto_safe: bool = True # 是否可安全自动执行（False 则需人工审核）
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_check": self.issue_check,
            "issue_message": self.issue_message,
            "severity": self.severity,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "old_code": self.old_code,
            "new_code": self.new_code,
            "description": self.description,
            "auto_safe": self.auto_safe,
        }


@dataclass
class FixPlan:
    """修复计划 — 包含一组 FixAction"""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    project_path: str = ""
    actions: List[FixAction] = field(default_factory=list)
    total_issues_addressed: int = 0
    auto_safe_count: int = 0
    needs_review_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "project_path": self.project_path,
            "total_issues_addressed": self.total_issues_addressed,
            "auto_safe_count": self.auto_safe_count,
            "needs_review_count": self.needs_review_count,
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass
class FixResult:
    """修复执行结果"""
    action: FixAction
    success: bool
    error: Optional[str] = None
    backed_up: bool = False
    backup_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.action.file_path,
            "issue_check": self.action.issue_check,
            "description": self.action.description,
            "success": self.success,
            "error": self.error,
            "backed_up": self.backed_up,
            "backup_path": self.backup_path,
        }


@dataclass
class ProjectProfile:
    """项目特征分析结果"""
    project_type: str
    tech_stack: List[str]
    complexity: str  # low, medium, high
    scale: str       # small, medium, large, enterprise
    domain: str      # 业务领域
    security_requirements: int  # 0-10
    file_count: int
    lines_of_code: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_type": self.project_type,
            "tech_stack": self.tech_stack,
            "complexity": self.complexity,
            "scale": self.scale,
            "domain": self.domain,
            "security_requirements": self.security_requirements,
            "file_count": self.file_count,
            "lines_of_code": self.lines_of_code,
        }


__all__ = ["ValidationResult", "RoundResult", "ProjectProfile", "FixAction", "FixPlan", "FixResult"]