<p align="center">
  <h1 align="center">iterative-qa</h1>
  <p align="center"><strong>AI 驱动的智能质量校验引擎</strong></p>
  <p align="center">
    <img src="https://img.shields.io/badge/version-3.0.0-blue" alt="Version">
    <img src="https://img.shields.io/badge/python-3.10+-green" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="License">
    <img src="https://img.shields.io/badge/status-production-success" alt="Status">
  </p>
  <p align="center">
    让 11 位 AI 专家多视角审视你的项目 &nbsp;·&nbsp; 大模型驱动 &nbsp;·&nbsp; 即插即用
  </p>
</p>

---

## 💡 一句话介绍

> 不是又一个 Linter。**iterative-qa** 像一支虚拟的 QA 团队——让 11 位 AI 视角专家围绕你的项目展开多轮交叉审查，直到所有问题收敛。

---

## 🎯 解决什么痛点？

| 传统质量检查 | iterative-qa |
|---|---|
| 单一视角（Linter / 单测覆盖） | 11 种视角专家联合审查 |
| 规则死板，配置繁琐 | AI 动态适配项目特征 |
| 只报错，不给修复路径 | 每一条 issue 附带 remediation |
| 一次扫完就结束 | **迭代收敛**——跑多轮直到无新问题 |
| 通用工具，不懂你的行业 | 内置医疗/金融/合规等领域专项 |

**核心逻辑**：扫描项目 → AI 推荐视角组合 → 多轮交互验证 → 问题收敛 → 输出可执行的质量报告。

---

## 🚀 30 秒上手

```bash
# 安装
pip install https://github.com/zhouliang-sjtu/iterative-qa/releases/download/v3.0.0/iterative_qa-3.0.0-py3-none-any.whl

# 一行分析项目
iterative-qa --analyze

# 一键执行完整质量校验
iterative-qa --full-cycle --report --output report.md
```

<details>
<summary>📦 源码安装</summary>

```bash
git clone https://github.com/zhouliang-sjtu/iterative-qa.git
cd iterative-qa
pip install -e .
```
</details>

---

## 🧠 核心能力

### 11 位视角专家联合审查

| 专家 | 关注点 | 自动激活条件 |
|---|---|---|
| **Developer** | 编译/类型/架构 | 所有项目 |
| **User** | 交互体验/可访问性 | Web/Mobile |
| **Security** | 漏洞/密钥/敏感文件 | 安全要求 ≥ 5 |
| **Healthcare** | HIPAA/HL7 FHIR/脱敏 | 医疗领域 |
| **Auditor** | 审计追溯/合规 | 金融/医疗/政府 |
| **Statistician** | 算法正确性/数据质量 | AI/Data 项目 |
| **Performance** | 负载/响应时间 | 大型项目 |
| **Compliance** | GDPR / ISO 27001 | 监管行业 |
| **Business** | 需求一致性/文档完整 | 业务系统 |
| **Architect** | 模块耦合/技术债务 | 企业级项目 |
| **DevOps** | 健康检查/Docker/可观测性 | 生产部署 |

**自适应推荐算法**：每个专家根据你的项目特征自动计算兼容性分数（0-1），高出阈值的自动加入审查队列。

### 四阶段分层扫描

```
阶段 0 — 环境基线检查
  依赖完整性 · 数据库连通 · 缓存服务 · 外部 API 可达性

阶段 1 — 静态深度分析
  编译检查 · 类型检查 · 导入检查 · 代码规范

阶段 2 — 运行时渐进验证
  启动日志 · 健康检查 · 认证流程 · API 端点测试

阶段 3 — 集成链路验证
  前后端联通 · 页面渲染 · 数据流完整性
```

### 迭代收敛机制

```
本轮发现 P0/P1 ──→ 继续下一轮
本轮仅 P2/P3    ──→ 再跑一轮确认
连续 2 轮无问题 ──→ ✅ 收敛，输出最终报告
```

---

## 🏥 医疗领域专项

上海交通大学医学院背景，天生具备医疗领域基因：

| 检查项 | 说明 |
|---|---|
| HIPAA 合规检查 | 自动检测医疗数据处理流程合规性 |
| 数据脱敏验证 | 确保患者隐私（姓名、身份证号、病历号）安全 |
| HL7 FHIR 标准 | 医疗数据交换标准兼容性检查 |
| 临床术语验证 | SNOMED CT、ICD-10 编码规范检查 |

```python
from iterative_qa import QAService
from iterative_qa.perspectives import HealthcareExpert

qa = QAService(project_path="/path/to/med-app")
qa.register_expert(HealthcareExpert())
result = qa.validate(round_number=1)
```

---

## 🤖 大模型支持

**iterative-qa 内置大模型驱动能力**，提供智能报告生成和项目深度分析。支持 7 种模型提供商，按需选择：

| 提供商 | 配置方式 |
|---|---|
| OpenAI (GPT-4o) | `LLM_PROVIDER=openai` |
| Anthropic (Claude) | `LLM_PROVIDER=anthropic` |
| Google (Gemini) | `LLM_PROVIDER=google` |
| 百度文心一言 | `LLM_PROVIDER=baidu` |
| 阿里通义千问 | `LLM_PROVIDER=tongyi` |
| 智谱 GLM | `LLM_PROVIDER=zhipu` |
| Hugging Face | `LLM_PROVIDER=huggingface` |

```bash
# 复制配置模板
cp .env.example .env

# 填入你的 API Key
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-xxxx
```

未配置时自动降级为规则引擎模式，无需大模型也能完整校验。

---

## 💻 API 使用

```python
from iterative_qa import QAService

qa = QAService(project_path="/path/to/project")

# 一键分析
profile = qa.analyze_project()
# → ProjectProfile(project_type="Web", tech_stack=["React","Python"], ...)

# 智能推荐审查视角
qa.recommend_perspectives()
# → ['developer', 'security', 'user', 'performance', 'devops']

# 执行校验
result = qa.validate(round_number=1)
for issue in result.issues_found:
    print(f"[{issue.severity}] {issue.check_name} → {issue.remediation}")

# LLM 驱动的智能报告
qa.generate_report(use_llm=True)

# 完整迭代周期（自动多轮直到收敛）
qa.run_full_cycle(max_rounds=10)
```

---

## 🔧 自定义扩展

```python
from iterative_qa import BasePerspectiveExpert, ValidationResult

class MyExpert(BasePerspectiveExpert):
    def get_name(self):
        return "my_expert"
    
    def get_compatibility(self, profile):
        return 0.9 if profile.get("domain") == "医疗" else 0.2
    
    def validate(self, profile):
        return [
            ValidationResult(
                check_name="my_check",
                status="warning",
                message="发现问题",
                severity="medium",
                remediation="修复建议"
            )
        ]

qa = QAService()
qa.register_expert(MyExpert)
```

---

## 📊 CLI 命令参考

| 参数 | 简写 | 说明 |
|---|---|---|
| `--path` | `-p` | 项目路径（默认当前目录） |
| `--round` | `-r` | 校验轮次 |
| `--full-cycle` | `-f` | 完整校验周期（自动收敛） |
| `--analyze` | `-a` | 仅分析项目特征 |
| `--report` | `-o` | 生成质量报告 |
| `--output` | — | 报告输出文件路径 |
| `--max-rounds` | — | 最大校验轮次（默认 10） |

---

## 📁 项目结构

```
iterative-qa/
├── .env.example          # 大模型环境配置模板（7种提供商）
├── iterative_qa.yaml     # 产品化策略配置
├── pyproject.toml        # 构建配置
├── requirements.txt      # 依赖清单
├── SKILL.md              # 技能规范（Trae 市场）
├── skill.yaml            # 技能元数据
├── iterative_qa/
│   ├── __init__.py       # 模块导出
│   ├── cli.py            # 命令行接口
│   ├── core.py           # QAService 核心引擎
│   ├── scanner.py        # 智能项目扫描器
│   ├── models.py         # 数据模型定义
│   ├── llm_service.py    # 多厂商大模型适配层
│   └── perspectives/
│       └── __init__.py   # 11 种视角专家
└── dist/                 # 构建产物（wheel / tar.gz）
```

---

## 🤝 贡献

1. Fork 本项目
2. 创建功能分支 `feature/xxx`
3. 提交代码（遵循 PEP 8）
4. 发起 Pull Request

---

## 💰 免费 + 捐赠

iterative-qa 完全免费。如果对你有帮助，欢迎：
- ⭐ **Star 这个项目**
- 💰 **GitHub Sponsors**: [sponsor/zhouliang-sjtu](https://github.com/sponsors/zhouliang-sjtu)
- 📢 **分享给更多开发者**

---

## 📄 许可证

MIT License © 2026 周良 · 上海交通大学医学院

---

<p align="center">
  <sub>Built with ❤️ at Shanghai Jiao Tong University School of Medicine</sub>
</p>
