"""视角专家模块 - 提供多种视角的质量验证能力"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import subprocess
import os


class ValidationResult:
    """验证结果"""
    def __init__(self, check_name: str, status: str, message: str, severity: str, remediation: Optional[str] = None):
        self.check_name = check_name
        self.status = status
        self.message = message
        self.severity = severity
        self.remediation = remediation
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status,
            "message": self.message,
            "severity": self.severity,
            "remediation": self.remediation,
        }


class BasePerspectiveExpert(ABC):
    """视角专家基类"""
    
    @abstractmethod
    def get_name(self) -> str:
        """获取视角名称"""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """获取视角描述"""
        pass
    
    @abstractmethod
    def get_compatibility(self, project_features: Dict[str, Any]) -> float:
        """计算与项目的兼容性（0-1）"""
        pass
    
    @abstractmethod
    def validate(self, project_features: Dict[str, Any]) -> List[ValidationResult]:
        """执行验证"""
        pass
    
    def optimize(self, data: Any) -> Any:
        """执行优化（可选）"""
        return data


class PerspectiveRegistry:
    """视角专家注册表"""
    
    def __init__(self):
        self.experts = {}
    
    def register_expert(self, expert_class):
        """注册视角专家"""
        instance = expert_class()
        self.experts[instance.get_name()] = expert_class
    
    def get_expert(self, name: str):
        """获取视角专家实例"""
        if name in self.experts:
            return self.experts[name]()
        return None
    
    def get_all_experts(self) -> List[str]:
        """获取所有专家名称"""
        return list(self.experts.keys())
    
    def recommend_experts(self, project_features: Dict[str, Any]) -> List[str]:
        """基于项目特征推荐视角专家"""
        recommendations = []
        
        for name, expert_class in self.experts.items():
            expert = expert_class()
            compatibility = expert.get_compatibility(project_features)
            if compatibility >= 0.3:
                recommendations.append({
                    "name": name,
                    "compatibility": compatibility
                })
        
        # 按兼容性排序
        recommendations.sort(key=lambda x: x["compatibility"], reverse=True)
        
        # 返回前5个最兼容的专家
        return [r["name"] for r in recommendations[:5]]


class DeveloperExpert(BasePerspectiveExpert):
    """开发者视角专家"""
    
    def get_name(self) -> str:
        return "developer"
    
    def get_description(self) -> str:
        return "代码质量、类型安全、架构设计验证"
    
    def get_compatibility(self, project_features: Dict[str, Any]) -> float:
        return 1.0  # 适用于所有项目
    
    def validate(self, project_features: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        
        # 检查 Python 编译
        try:
            result = subprocess.run(
                ["python", "-m", "compileall", "-q", "."],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                results.append(ValidationResult(
                    check_name="python_compile",
                    status="failed",
                    message=f"Python编译错误: {result.stderr}",
                    severity="high",
                    remediation="修复Python语法错误"
                ))
            else:
                results.append(ValidationResult(
                    check_name="python_compile",
                    status="passed",
                    message="Python编译通过",
                    severity="low"
                ))
        except Exception as e:
            results.append(ValidationResult(
                check_name="python_compile",
                status="warning",
                message=f"编译检查失败: {str(e)}",
                severity="medium"
            ))
        
        # 检查 TypeScript 编译
        if "TypeScript" in project_features.get("tech_stack", []):
            try:
                result = subprocess.run(
                    ["npx", "tsc", "--noEmit"],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode != 0:
                    results.append(ValidationResult(
                        check_name="typescript_compile",
                        status="failed",
                        message=f"TypeScript编译错误: {result.stderr}",
                        severity="high",
                        remediation="修复TypeScript类型错误"
                    ))
                else:
                    results.append(ValidationResult(
                        check_name="typescript_compile",
                        status="passed",
                        message="TypeScript编译通过",
                        severity="low"
                    ))
            except Exception as e:
                results.append(ValidationResult(
                    check_name="typescript_compile",
                    status="warning",
                    message=f"TypeScript检查失败: {str(e)}",
                    severity="medium"
                ))
        
        # 检查依赖文件
        if os.path.exists("requirements.txt"):
            results.append(ValidationResult(
                check_name="requirements_exists",
                status="passed",
                message="requirements.txt 存在",
                severity="low"
            ))
        elif os.path.exists("pyproject.toml"):
            results.append(ValidationResult(
                check_name="requirements_exists",
                status="passed",
                message="pyproject.toml 存在",
                severity="low"
            ))
        else:
            results.append(ValidationResult(
                check_name="requirements_exists",
                status="warning",
                message="未找到依赖管理文件",
                severity="medium",
                remediation="创建 requirements.txt 或 pyproject.toml"
            ))
        
        return results


class SecurityExpert(BasePerspectiveExpert):
    """安全工程师视角专家"""
    
    def get_name(self) -> str:
        return "security"
    
    def get_description(self) -> str:
        return "漏洞扫描、渗透测试、数据加密验证"
    
    def get_compatibility(self, project_features: Dict[str, Any]) -> float:
        domain = project_features.get("domain", "")
        security_req = project_features.get("security_requirements", 5) / 10
        
        if domain in ["金融", "医疗", "政府"]:
            return min(1.0, 0.8 + security_req * 0.2)
        return security_req * 0.7
    
    def validate(self, project_features: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        
        # 检查敏感文件
        sensitive_files = [".env", "secrets.json", "credentials.json"]
        for filename in sensitive_files:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if any(keyword in content.lower() for keyword in ["password", "secret", "key"]):
                        results.append(ValidationResult(
                            check_name=f"sensitive_file_{filename}",
                            status="warning",
                            message=f"敏感文件 {filename} 可能包含敏感信息",
                            severity="medium",
                            remediation="确保敏感文件不提交到版本控制"
                        ))
        
        # 检查 .gitignore
        if os.path.exists(".gitignore"):
            with open(".gitignore", 'r', encoding='utf-8') as f:
                content = f.read()
                if ".env" not in content:
                    results.append(ValidationResult(
                        check_name="gitignore_env",
                        status="warning",
                        message=".gitignore 未忽略 .env 文件",
                        severity="medium",
                        remediation="在 .gitignore 中添加 .env"
                    ))
        else:
            results.append(ValidationResult(
                check_name="gitignore_exists",
                status="warning",
                message="未找到 .gitignore 文件",
                severity="medium",
                remediation="创建 .gitignore 文件"
            ))
        
        return results


class HealthcareExpert(BasePerspectiveExpert):
    """医疗健康领域专家"""
    
    def get_name(self) -> str:
        return "healthcare"
    
    def get_description(self) -> str:
        return "医疗数据合规性、HIPAA合规、数据脱敏验证"
    
    def get_compatibility(self, project_features: Dict[str, Any]) -> float:
        domain = project_features.get("domain", "")
        if domain in ["医疗", "健康"]:
            return 0.95
        # 检查是否包含医疗相关关键词
        tech_stack = project_features.get("tech_stack", [])
        if any(t.lower() in ["healthcare", "medical", "patient"] for t in tech_stack):
            return 0.7
        return 0.1
    
    def validate(self, project_features: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        
        # HIPAA 合规检查
        results.append(ValidationResult(
            check_name="hipaa_compliance",
            status="warning",
            message="建议进行HIPAA合规性评估",
            severity="medium",
            remediation="审查患者数据处理流程，确保符合HIPAA要求"
        ))
        
        # 数据脱敏检查
        results.append(ValidationResult(
            check_name="data_desensitization",
            status="warning",
            message="建议实施数据脱敏策略",
            severity="medium",
            remediation="对患者隐私数据（姓名、身份证号、病历号等）进行脱敏处理"
        ))
        
        # HL7 FHIR 标准检查
        results.append(ValidationResult(
            check_name="hl7_fhir_check",
            status="info",
            message="建议采用HL7 FHIR标准进行医疗数据交换",
            severity="low",
            remediation="考虑集成HL7 FHIR标准接口"
        ))
        
        return results


class AuditorExpert(BasePerspectiveExpert):
    """审计员视角专家"""
    
    def get_name(self) -> str:
        return "auditor"
    
    def get_description(self) -> str:
        return "合规性、可追溯性、审计日志验证"
    
    def get_compatibility(self, project_features: Dict[str, Any]) -> float:
        domain = project_features.get("domain", "")
        if domain in ["金融", "医疗", "政府"]:
            return 0.9
        return 0.5
    
    def validate(self, project_features: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        
        # 检查日志配置
        results.append(ValidationResult(
            check_name="audit_logging",
            status="info",
            message="建议配置审计日志",
            severity="low",
            remediation="确保关键操作（登录、数据修改、权限变更）有完整的审计记录"
        ))
        
        # GDPR 合规检查
        results.append(ValidationResult(
            check_name="gdpr_compliance",
            status="info",
            message="建议进行GDPR合规性评估",
            severity="low",
            remediation="审查数据处理流程，确保符合GDPR要求"
        ))
        
        return results


class StatisticianExpert(BasePerspectiveExpert):
    """统计专家视角专家"""
    
    def get_name(self) -> str:
        return "statistician"
    
    def get_description(self) -> str:
        return "算法正确性、数据质量、模型验证"
    
    def get_compatibility(self, project_features: Dict[str, Any]) -> float:
        project_type = project_features.get("project_type", "")
        if project_type in ["Data", "AI"]:
            return 0.95
        
        tech_stack = project_features.get("tech_stack", [])
        data_techs = ["pandas", "numpy", "scikit-learn", "tensorflow", "pytorch"]
        if any(t.lower() in [tech.lower() for tech in tech_stack] for t in data_techs):
            return 0.7
        
        return 0.2
    
    def validate(self, project_features: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        
        # 检查数据验证逻辑
        results.append(ValidationResult(
            check_name="data_validation",
            status="info",
            message="建议实施数据质量验证",
            severity="low",
            remediation="对输入数据进行完整性、准确性、一致性检查"
        ))
        
        # 检查模型评估
        if project_features.get("project_type") == "AI":
            results.append(ValidationResult(
                check_name="model_validation",
                status="info",
                message="建议实施模型验证流程",
                severity="low",
                remediation="确保模型有完整的评估指标和验证数据集"
            ))
        
        return results


class PerformanceExpert(BasePerspectiveExpert):
    """性能工程师视角专家"""
    
    def get_name(self) -> str:
        return "performance"
    
    def get_description(self) -> str:
        return "负载测试、响应时间、资源消耗验证"
    
    def get_compatibility(self, project_features: Dict[str, Any]) -> float:
        scale = project_features.get("scale", "small")
        scale_weights = {"small": 0.3, "medium": 0.6, "large": 0.8, "enterprise": 1.0}
        return scale_weights.get(scale, 0.5)
    
    def validate(self, project_features: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        
        # 性能测试建议
        results.append(ValidationResult(
            check_name="performance_testing",
            status="info",
            message="建议实施性能测试",
            severity="low",
            remediation="使用 JMeter 或 Locust 进行负载测试"
        ))
        
        # 代码复杂度检查
        lines_of_code = project_features.get("lines_of_code", 0)
        if lines_of_code > 50000:
            results.append(ValidationResult(
                check_name="code_complexity",
                status="warning",
                message="代码量较大，建议进行性能优化",
                severity="medium",
                remediation="进行代码审查，优化关键路径性能"
            ))
        
        return results


class ComplianceExpert(BasePerspectiveExpert):
    """合规专家视角专家"""
    
    def get_name(self) -> str:
        return "compliance"
    
    def get_description(self) -> str:
        return "行业标准合规性验证（GDPR、ISO27001等）"
    
    def get_compatibility(self, project_features: Dict[str, Any]) -> float:
        domain = project_features.get("domain", "")
        if domain in ["金融", "医疗", "政府"]:
            return 0.9
        return 0.4
    
    def validate(self, project_features: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        
        # ISO 27001 合规检查
        results.append(ValidationResult(
            check_name="iso27001_compliance",
            status="info",
            message="建议进行ISO 27001信息安全管理体系认证",
            severity="low",
            remediation="建立信息安全管理体系"
        ))
        
        return results


class BusinessExpert(BasePerspectiveExpert):
    """业务分析师视角专家"""
    
    def get_name(self) -> str:
        return "business"
    
    def get_description(self) -> str:
        return "需求一致性、业务流程正确性验证"
    
    def get_compatibility(self, project_features: Dict[str, Any]) -> float:
        return 0.6  # 适用于大多数业务系统
    
    def validate(self, project_features: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        
        # 需求文档检查
        docs = ["README.md", "docs/", "requirements.txt", "specs/"]
        has_docs = any(os.path.exists(doc) for doc in docs)
        
        if has_docs:
            results.append(ValidationResult(
                check_name="documentation_exists",
                status="passed",
                message="项目文档存在",
                severity="low"
            ))
        else:
            results.append(ValidationResult(
                check_name="documentation_exists",
                status="warning",
                message="建议添加项目文档",
                severity="medium",
                remediation="创建 README.md 和需求文档"
            ))
        
        return results


class ArchitectExpert(BasePerspectiveExpert):
    """架构师视角专家"""
    
    def get_name(self) -> str:
        return "architect"
    
    def get_description(self) -> str:
        return "系统架构、模块耦合、技术债务评估"
    
    def get_compatibility(self, project_features: Dict[str, Any]) -> float:
        scale = project_features.get("scale", "small")
        scale_weights = {"small": 0.3, "medium": 0.5, "large": 0.8, "enterprise": 1.0}
        return scale_weights.get(scale, 0.5)
    
    def validate(self, project_features: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        
        # 架构文档检查
        if os.path.exists("docs/") or os.path.exists("architecture.md"):
            results.append(ValidationResult(
                check_name="architecture_docs",
                status="passed",
                message="架构文档存在",
                severity="low"
            ))
        else:
            results.append(ValidationResult(
                check_name="architecture_docs",
                status="warning",
                message="建议添加架构文档",
                severity="medium",
                remediation="创建架构设计文档"
            ))
        
        return results


class DevOpsExpert(BasePerspectiveExpert):
    """运维工程师视角专家"""
    
    def get_name(self) -> str:
        return "devops"
    
    def get_description(self) -> str:
        return "可观测性、容错能力、扩展性验证"
    
    def get_compatibility(self, project_features: Dict[str, Any]) -> float:
        scale = project_features.get("scale", "small")
        scale_weights = {"small": 0.2, "medium": 0.5, "large": 0.8, "enterprise": 1.0}
        return scale_weights.get(scale, 0.4)
    
    def validate(self, project_features: Dict[str, Any]) -> List[ValidationResult]:
        results = []
        
        # Docker 配置检查
        if os.path.exists("Dockerfile") or os.path.exists("docker-compose.yml"):
            results.append(ValidationResult(
                check_name="docker_config",
                status="passed",
                message="Docker配置存在",
                severity="low"
            ))
        else:
            results.append(ValidationResult(
                check_name="docker_config",
                status="warning",
                message="建议添加Docker配置",
                severity="medium",
                remediation="创建 Dockerfile 和 docker-compose.yml"
            ))
        
        # 健康检查端点检查
        results.append(ValidationResult(
            check_name="health_check",
            status="info",
            message="建议配置健康检查端点",
            severity="low",
            remediation="实现 /health 端点用于健康检查"
        ))
        
        return results


class UserExpert(BasePerspectiveExpert):
    """用户视角专家 - 从最终用户角度验证产品质量"""
    
    def get_name(self) -> str:
        return "user"
    
    def get_description(self) -> str:
        return "用户体验、可用性、界面友好性验证"
    
    def get_compatibility(self, project_features: Dict[str, Any]) -> float:
        """
        根据项目特征计算与用户视角的兼容性
        - Web/Mobile项目兼容性最高（直接面向用户）
        - 后端服务兼容性较低（间接面向用户）
        - 嵌入式系统兼容性最低
        """
        project_type = project_features.get("project_type", "")
        
        # 用户直接使用的项目类型
        user_facing_types = ["Web", "Mobile", "Desktop"]
        if project_type in user_facing_types:
            return 0.95
        
        # 后端服务（间接面向用户）
        if project_type == "Backend":
            return 0.6
        
        # 数据/AI项目（可能有用户界面）
        if project_type in ["Data", "AI"]:
            tech_stack = project_features.get("tech_stack", [])
            if any(t.lower() in ["react", "vue", "frontend", "ui"] for t in tech_stack):
                return 0.8
            return 0.5
        
        # 嵌入式系统（兼容性最低）
        if project_type == "Embedded":
            return 0.3
        
        return 0.7  # 默认中等兼容性
    
    def validate(self, project_features: Dict[str, Any]) -> List[ValidationResult]:
        """从用户视角执行验证"""
        results = []
        
        project_type = project_features.get("project_type", "")
        tech_stack = project_features.get("tech_stack", [])
        
        # 1. 用户界面检查
        if project_type in ["Web", "Mobile", "Desktop"]:
            # 检查前端框架是否存在
            frontend_frameworks = ["React", "Vue", "Angular", "Svelte"]
            has_frontend = any(f in tech_stack for f in frontend_frameworks)
            
            if has_frontend:
                results.append(ValidationResult(
                    check_name="frontend_framework",
                    status="passed",
                    message="使用了现代化前端框架，用户体验有保障",
                    severity="low"
                ))
            else:
                results.append(ValidationResult(
                    check_name="frontend_framework",
                    status="warning",
                    message="未检测到现代化前端框架",
                    severity="medium",
                    remediation="考虑使用 React、Vue 等现代化前端框架提升用户体验"
                ))
            
            # 检查是否有UI组件库
            ui_libraries = ["Ant Design", "Material UI", "Element Plus", "Tailwind CSS"]
            has_ui_lib = any(lib.lower() in ' '.join(tech_stack).lower() for lib in ui_libraries)
            
            if has_ui_lib:
                results.append(ValidationResult(
                    check_name="ui_library",
                    status="passed",
                    message="使用了专业UI组件库",
                    severity="low"
                ))
            else:
                results.append(ValidationResult(
                    check_name="ui_library",
                    status="info",
                    message="建议使用专业UI组件库",
                    severity="low",
                    remediation="考虑使用 Ant Design、Material UI 等组件库"
                ))
        
        # 2. 可访问性检查
        results.append(ValidationResult(
            check_name="accessibility",
            status="info",
            message="建议进行可访问性测试",
            severity="low",
            remediation="确保应用支持屏幕阅读器、键盘导航等辅助功能"
        ))
        
        # 3. 响应式设计检查（针对Web项目）
        if project_type == "Web":
            results.append(ValidationResult(
                check_name="responsive_design",
                status="info",
                message="建议实现响应式设计",
                severity="low",
                remediation="确保网站在不同设备上都能良好显示"
            ))
        
        # 4. 加载性能检查
        results.append(ValidationResult(
            check_name="load_performance",
            status="info",
            message="建议优化页面加载速度",
            severity="low",
            remediation="使用懒加载、代码分割、图片压缩等技术"
        ))
        
        # 5. 用户反馈机制检查
        results.append(ValidationResult(
            check_name="user_feedback",
            status="info",
            message="建议添加用户反馈机制",
            severity="low",
            remediation="实现用户反馈表单、满意度调查等功能"
        ))
        
        # 6. 错误提示友好性检查
        results.append(ValidationResult(
            check_name="error_messages",
            status="info",
            message="建议优化错误提示信息",
            severity="low",
            remediation="使用用户友好的错误提示，避免技术术语"
        ))
        
        # 7. 医疗领域特殊检查
        domain = project_features.get("domain", "")
        if domain == "医疗":
            results.append(ValidationResult(
                check_name="healthcare_usability",
                status="info",
                message="医疗应用需特别关注用户易用性",
                severity="medium",
                remediation="针对患者和医护人员设计直观的操作界面"
            ))
        
        return results


# 导出所有专家类
__all__ = [
    "BasePerspectiveExpert",
    "PerspectiveRegistry",
    "ValidationResult",
    "DeveloperExpert",
    "UserExpert",
    "SecurityExpert",
    "HealthcareExpert",
    "AuditorExpert",
    "StatisticianExpert",
    "PerformanceExpert",
    "ComplianceExpert",
    "BusinessExpert",
    "ArchitectExpert",
    "DevOpsExpert",
]