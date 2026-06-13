# iterative-qa - AI驱动的智能质量校验引擎

> 通过大模型分析项目特征，动态识别最优验证视角，实现精准的多维度质量审计与工程优化

## 🌟 核心特性

- **智能项目扫描**: 自动分析项目结构、技术栈、规模和业务领域
- **动态视角识别**: 基于项目特征自动推荐最合适的质量校验视角组合
- **动态专家系统**: 11种视角专家，自动适配不同项目类型（Web/移动/数据/AI/嵌入式）
- **四阶段分层扫描**: 环境基线→静态分析→运行时验证→集成验证
- **智能问题分类**: 自动分类问题等级和类型，提供修复建议
- **质量报告生成**: 专业质量报告自动生成
- **医疗领域专项**: 针对医疗健康领域的专项优化

## 🚀 快速开始

### 安装方式

#### 方式一：pip 安装（推荐）

```bash
pip install iterative-qa
```

#### 方式二：源码安装

```bash
git clone https://github.com/shsmu-zhouliang/iterative-qa.git
cd iterative-qa
pip install -e .
```

### 使用方式

#### 方式一：命令行调用

```bash
# 分析项目特征
iterative-qa --analyze

# 执行第1轮质量校验
iterative-qa --round 1

# 指定项目路径
iterative-qa --path /path/to/project --round 1

# 执行完整校验周期直到收敛
iterative-qa --full-cycle

# 生成详细报告
iterative-qa --report --output report.md
```

**命令行参数说明**:

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--path`, `-p` | 项目路径 | 当前目录 |
| `--round`, `-r` | 校验轮次 | 1 |
| `--full-cycle`, `-f` | 执行完整校验周期 | 否 |
| `--analyze`, `-a` | 仅分析项目特征 | 否 |
| `--report`, `-o` | 生成质量报告 | 否 |
| `--output` | 报告输出文件路径 | 无 |
| `--max-rounds` | 最大校验轮次 | 10 |

#### 方式二：API 调用

```python
from iterative_qa import QAService

# 初始化服务（可指定项目路径）
qa_service = QAService(project_path="/path/to/project")

# 分析项目特征
project_profile = qa_service.analyze_project()
print(f"项目类型: {project_profile.project_type}")
print(f"技术栈: {project_profile.tech_stack}")
print(f"规模: {project_profile.scale}")
print(f"领域: {project_profile.domain}")

# 获取推荐视角专家
perspectives = qa_service.recommend_perspectives()
print(f"推荐视角: {perspectives}")

# 执行质量校验（指定轮次）
result = qa_service.validate(round_number=1)
print(f"校验状态: {result.status}")
print(f"发现问题: {len(result.issues_found)}")

# 检查收敛状态
is_converged = qa_service.is_converged()
print(f"是否收敛: {'是' if is_converged else '否'}")

# 生成质量报告
report = qa_service.generate_report()
print(report)
```

## 🧠 智能视角专家系统

### 内置视角专家

| 视角专家 | 适用场景 | 验证重点 |
|----------|----------|----------|
| DeveloperExpert | 所有项目 | 代码质量、类型安全、架构设计 |
| UserExpert | 面向用户的项目 | 用户体验、可用性、界面友好性 |
| SecurityExpert | 敏感数据项目 | 漏洞扫描、渗透测试、数据加密 |
| HealthcareExpert | 医疗健康领域 | HIPAA合规、数据脱敏、临床标准 |
| AuditorExpert | 金融/政府/医疗 | 合规性、可追溯性、审计日志 |
| StatisticianExpert | 数据/AI项目 | 算法正确性、数据质量、模型验证 |
| PerformanceExpert | 高并发系统 | 负载测试、响应时间、资源消耗 |
| ComplianceExpert | 监管行业 | GDPR/ISO27001/行业标准 |
| BusinessExpert | 业务系统 | 需求一致性、业务流程正确性 |
| ArchitectExpert | 大型系统 | 系统架构、模块耦合、技术债务 |
| DevOpsExpert | 生产环境部署 | 可观测性、容错能力、扩展性 |

### 视角选择算法

系统会自动：
1. 扫描项目特征（技术栈、规模、领域、安全要求等）
2. 计算每个视角专家的兼容性分数（0-1）
3. 根据兼容性阈值（默认 0.3）筛选视角专家
4. 按兼容性优先级排序执行验证

## 🔍 四阶段分层扫描

```
阶段0: 环境基线检查
  └─ 依赖完整性、数据库连通、缓存服务、外部API

阶段1: 静态深度分析
  └─ 编译检查、类型检查、导入检查、ORM关系验证

阶段2: 运行时渐进验证
  └─ 启动日志审计、健康检查、认证流程、API测试

阶段3: 集成链路验证
  └─ 前后端联通、页面渲染、数据流完整

阶段4: 回归深度清理
  └─ 修复副作用检测、全量回归测试
```

## 📊 问题分级体系

| 等级 | 定义 | 响应时间 |
|------|------|----------|
| **P0** | 服务不可启动 / 核心功能不可用 | 立即修复 |
| **P1** | 部分功能异常 / 数据不完整 | 本迭代修复 |
| **P2** | 不影响功能但不符合最佳实践 | 记录，后续修复 |
| **P3** | 优化建议 / 非关键问题 | 记录到backlog |

## 📈 收敛判定标准

| 状态 | 标准 | 行动 |
|------|------|------|
| 未收敛 | 本轮发现 ≥ 1 个 P0/P1 | 继续下一轮 |
| 趋于收敛 | 本轮仅发现 P2/P3 | 再跑一轮确认 |
| 已收敛 | 连续 2 轮无新 P0/P1/P2 | 输出最终报告 |

## 🏥 医疗健康领域专项支持

系统针对医疗健康领域提供专项优化，包括：

### 医疗领域视角增强

| 检查项 | 描述 |
|--------|------|
| HIPAA合规检查 | 自动检测医疗数据处理合规性 |
| 数据脱敏验证 | 确保患者隐私数据安全 |
| 临床数据标准 | HL7 FHIR 标准兼容性检查 |
| 医疗术语验证 | SNOMED CT、ICD-10 编码验证 |

### 慢病管理专项检查示例

```python
from iterative_qa import QAService
from iterative_qa.perspectives import HealthcareExpert

qa_service = QAService(project_path="/path/to/healthcare-project")
qa_service.register_expert(HealthcareExpert())

result = qa_service.validate(round_number=1)
report = qa_service.generate_report()
print(report)
```

## 🔧 自定义扩展

### 添加自定义视角专家

```python
from iterative_qa import BasePerspectiveExpert

class MyCustomExpert(BasePerspectiveExpert):
    def get_name(self):
        return "MyCustomExpert"
    
    def get_description(self):
        return "自定义视角专家"
    
    def get_compatibility(self, project_features):
        if project_features.get("domain") == "医疗":
            return 0.9
        return 0.3
    
    def validate(self, project_features):
        results = []
        if not os.path.exists("custom_config.yaml"):
            results.append(ValidationResult(
                check_name="custom_config_exists",
                status="warning",
                message="缺少自定义配置文件",
                severity="medium",
                remediation="创建 custom_config.yaml"
            ))
        return results
    
    def optimize(self, data):
        return data

qa_service = QAService()
qa_service.register_expert(MyCustomExpert)
```

### 配置验证策略

```yaml
# iterative_qa.yaml
perspectives:
  - name: developer
    enabled: true
    priority: high
  
  - name: security
    enabled: true
    priority: high
  
  - name: healthcare
    enabled: true
    priority: medium

validation:
  max_rounds: 10
  convergence_threshold: 2
  auto_fix: true
```

## 📁 项目结构

```
iterative-qa/
├── .trae/
│   └── skills/
│       └── iterative-qa/
│           ├── SKILL.md          # 技能规范文档
│           ├── skill.yaml        # 技能配置
│           ├── README.md         # 使用文档
│           ├── requirements.txt  # 依赖清单
│           ├── setup.py          # 安装配置
│           └── iterative_qa/     # 核心模块
│               ├── __init__.py
│               ├── core.py       # 核心服务类
│               ├── scanner.py    # 智能项目扫描器
│               ├── cli.py        # 命令行接口
│               └── perspectives/ # 视角专家模块
│                   └── __init__.py
└── tests/                        # 测试套件
```

## 🧪 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_core.py

# 生成测试报告
pytest --cov=iterative_qa --cov-report=html
```

## 📝 API 参考

### QAService 类

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `__init__(project_path)` | 初始化服务 | QAService |
| `analyze_project()` | 分析项目特征 | ProjectProfile |
| `recommend_perspectives()` | 获取推荐视角 | List[str] |
| `validate(round_number)` | 执行质量校验 | RoundResult |
| `is_converged()` | 检查收敛状态 | bool |
| `generate_report()` | 生成质量报告 | str |
| `run_full_cycle(max_rounds)` | 执行完整校验周期 | str |
| `register_expert(expert_class)` | 注册自定义专家 | None |

### ProjectProfile 类

| 属性 | 类型 | 说明 |
|------|------|------|
| `project_type` | str | 项目类型（Web/Mobile/Data/AI等） |
| `tech_stack` | List[str] | 技术栈列表 |
| `complexity` | str | 复杂度（low/medium/high） |
| `scale` | str | 规模（small/medium/large/enterprise） |
| `domain` | str | 业务领域（金融/医疗/电商等） |
| `security_requirements` | int | 安全要求等级（1-10） |
| `file_count` | int | 文件数量 |
| `lines_of_code` | int | 代码行数 |

## 🤝 贡献指南

欢迎贡献代码！请遵循以下流程：

1. Fork 项目
2. 创建功能分支（`feature/xxx`）
3. 提交代码（遵循 PEP8 规范）
4. 创建 Pull Request
5. 通过 CI 测试

## 📄 许可证

MIT License

## 📞 联系方式

- **作者**: 周良
- **邮箱**: zhouliang@shsmu.edu.cn
- **组织**: 上海交通大学医学院

---

**版本**: 3.0.0  
**状态**: ✅ 生产就绪  
**最后更新**: 2026-06-13