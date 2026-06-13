# iterative-qa 发布指南

## 📦 PyPI 发布流程

### 1. 准备工作

```bash
# 安装构建工具
pip install setuptools wheel twine

# 配置 PyPI 凭据
# 创建 ~/.pypirc 文件：
# [pypi]
# username = __token__
# password = your-pypi-api-token
```

### 2. 构建发布包

```bash
# 清理旧构建
rm -rf dist/ build/ *.egg-info/

# 构建 sdist 和 wheel
python setup.py sdist bdist_wheel

# 或使用 pyproject.toml
python -m build
```

### 3. 上传到 PyPI

```bash
# 测试环境（可选）
twine upload --repository testpypi dist/*

# 正式环境
twine upload dist/*
```

### 4. 验证发布

```bash
# 安装测试
pip install iterative-qa

# 验证版本
python -c "from iterative_qa import __version__; print(__version__)"
```

---

## 🤖 Trae AI 市场发布流程

### 1. 准备技能包

确保以下文件完整：
- `SKILL.md` - 技能描述文档
- `skill.yaml` - 技能元数据配置
- `README.md` - 使用文档
- `requirements.txt` - 依赖清单
- `setup.py` / `pyproject.toml` - 安装配置

### 2. 配置 skill.yaml

确保包含完整的元信息：
- name: 技能名称
- version: 版本号
- description: 技能描述
- author: 作者信息
- category: 分类
- tags: 标签
- features: 功能特性
- pricing: 定价方案

### 3. 打包上传

```bash
# 创建技能包（ZIP格式）
zip -r iterative-qa-skill.zip iterative_qa/ SKILL.md skill.yaml README.md requirements.txt

# 或使用官方 CLI（如果可用）
trae-cli skill upload iterative-qa-skill.zip
```

---

## 📝 版本发布清单

### 发布前检查

- [ ] 更新版本号 (`setup.py`, `pyproject.toml`, `__init__.py`)
- [ ] 更新 CHANGELOG.md（如有）
- [ ] 运行测试确保代码质量
- [ ] 验证 README.md 文档完整
- [ ] 确认 LICENSE 文件存在
- [ ] 更新 skill.yaml 版本号

### 发布步骤

1. **代码审查** - 确保代码符合规范
2. **运行测试** - `pytest`
3. **构建包** - `python -m build`
4. **上传 PyPI** - `twine upload dist/*`
5. **上传 Trae AI 市场** - 使用官方工具或平台
6. **发布 GitHub Release** - 创建版本标签

---

## 🔄 版本号管理

遵循语义化版本规范：

| 版本类型 | 格式 | 示例 |
|----------|------|------|
| 主版本 | MAJOR | 3.0.0 |
| 次版本 | MINOR | 3.1.0 |
| 补丁 | PATCH | 3.1.1 |

---

## 🚨 常见问题

### Q: 构建失败
```bash
# 确保安装了最新工具
pip install --upgrade setuptools wheel build
```

### Q: 上传失败（403）
- 检查 PyPI API Token 是否正确
- 确保 Token 具有上传权限

### Q: 依赖冲突
- 使用虚拟环境
- 检查 requirements.txt 版本约束

---

## 📞 联系方式

- 作者: 周良
- 邮箱: zhouliang@shsmu.edu.cn
- GitHub: https://github.com/zhouliang-sjtu/iterative-qa