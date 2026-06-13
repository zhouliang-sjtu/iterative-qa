"""核心服务类 - 提供完整的质量校验流程"""

import os
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, UTC
from dataclasses import dataclass, field

from .scanner import ProjectScanner
from .perspectives import PerspectiveRegistry


@dataclass
class ValidationResult:
    """验证结果"""
    check_name: str
    status: str  # passed, failed, warning
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


class QAService:
    """智能质量校验服务"""
    
    def __init__(self, project_path: str = ".", config: Optional[Dict] = None):
        self.project_path = project_path
        self.config = config or {}
        self.scanner = ProjectScanner()
        self.registry = PerspectiveRegistry()
        self.round_results: List[RoundResult] = []
        self.project_profile: Optional[ProjectProfile] = None
        
        # 初始化内置视角专家
        self._init_default_experts()
    
    def _init_default_experts(self):
        """初始化内置视角专家"""
        from .perspectives import (
            DeveloperExpert,
            SecurityExpert,
            HealthcareExpert,
            AuditorExpert,
            StatisticianExpert,
            PerformanceExpert,
            ComplianceExpert,
            BusinessExpert,
            ArchitectExpert,
            DevOpsExpert,
        )
        
        experts = [
            DeveloperExpert,
            SecurityExpert,
            HealthcareExpert,
            AuditorExpert,
            StatisticianExpert,
            PerformanceExpert,
            ComplianceExpert,
            BusinessExpert,
            ArchitectExpert,
            DevOpsExpert,
        ]
        
        for expert_class in experts:
            self.registry.register_expert(expert_class)
    
    def analyze_project(self) -> ProjectProfile:
        """分析项目特征"""
        self.project_profile = self.scanner.scan(self.project_path)
        return self.project_profile
    
    def recommend_perspectives(self) -> List[str]:
        """基于项目特征推荐视角专家"""
        if not self.project_profile:
            self.analyze_project()
        
        return self.registry.recommend_experts(self.project_profile.to_dict())
    
    def validate(self, round_number: int = 1) -> RoundResult:
        """执行质量校验"""
        # 确保项目已分析
        if not self.project_profile:
            self.analyze_project()
        
        # 获取推荐的视角专家
        recommended_experts = self.recommend_perspectives()
        
        # 执行验证
        results = []
        for expert_name in recommended_experts:
            expert = self.registry.get_expert(expert_name)
            if expert:
                expert_results = expert.validate(self.project_profile.to_dict())
                results.extend(expert_results)
        
        # 整理结果
        round_result = RoundResult(
            round_number=round_number,
            issues_found=results,
            status=self._determine_status(results),
        )
        
        self.round_results.append(round_result)
        return round_result
    
    def _determine_status(self, results: List[ValidationResult]) -> str:
        """确定校验状态"""
        has_critical = any(r.severity in ["critical", "high"] for r in results)
        if has_critical:
            return "failed"
        has_warning = any(r.status == "warning" for r in results)
        if has_warning:
            return "warning"
        return "passed"
    
    def is_converged(self) -> bool:
        """检查是否收敛"""
        if len(self.round_results) < 2:
            return False
        
        last_two = self.round_results[-2:]
        has_p0_p1 = any(
            any(r.severity in ["critical", "high"] for r in round_result.issues_found)
            for round_result in last_two
        )
        has_p2 = any(
            any(r.severity == "medium" for r in round_result.issues_found)
            for round_result in last_two
        )
        
        return not (has_p0_p1 or has_p2)
    
    def generate_report(self) -> str:
        """生成质量报告"""
        if not self.project_profile:
            return "请先执行项目分析"
        
        report = []
        report.append("# 质量校验报告")
        report.append(f"\n**项目名称**: {os.path.basename(self.project_path)}")
        report.append(f"**项目类型**: {self.project_profile.project_type}")
        report.append(f"**技术栈**: {', '.join(self.project_profile.tech_stack)}")
        report.append(f"**规模**: {self.project_profile.scale}")
        report.append(f"**领域**: {self.project_profile.domain}")
        report.append(f"**校验轮次**: {len(self.round_results)}")
        report.append(f"**收敛状态**: {'已收敛' if self.is_converged() else '未收敛'}")
        
        # 添加每轮结果
        for round_result in self.round_results:
            report.append(f"\n## 第{round_result.round_number}轮")
            report.append(f"- 时间: {round_result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            report.append(f"- 状态: {round_result.status}")
            report.append(f"- 发现问题: {len(round_result.issues_found)}")
            
            for issue in round_result.issues_found:
                report.append(f"\n### {issue.check_name}")
                report.append(f"- 状态: {issue.status}")
                report.append(f"- 严重程度: {issue.severity}")
                report.append(f"- 描述: {issue.message}")
                if issue.remediation:
                    report.append(f"- 修复建议: {issue.remediation}")
        
        return "\n".join(report)
    
    def register_expert(self, expert_class):
        """注册自定义视角专家"""
        self.registry.register_expert(expert_class)
    
    def run_full_cycle(self, max_rounds: int = 10) -> str:
        """执行完整的校验周期"""
        report = ["# 完整质量校验周期报告"]
        report.append(f"\n**项目**: {os.path.basename(self.project_path)}")
        report.append(f"**开始时间**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}")
        
        for round_num in range(1, max_rounds + 1):
            report.append(f"\n---\n## 第{round_num}轮校验")
            
            try:
                result = self.validate(round_num)
                report.append(f"- 状态: {result.status}")
                report.append(f"- 发现问题: {len(result.issues_found)}")
                
                if self.is_converged():
                    report.append("\n✅ 系统已收敛！")
                    break
                
            except Exception as e:
                report.append(f"- 错误: {str(e)}")
                break
        
        report.append(f"\n**结束时间**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"**总轮次**: {len(self.round_results)}")
        report.append(f"**最终状态**: {'已收敛' if self.is_converged() else '未收敛'}")
        
        return "\n".join(report)