"""iterative-qa - AI驱动的智能质量校验引擎 — 26位专家 × 5种能力 × 全链路覆盖"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="iterative-qa",
    version="4.0.0",
    author="周良",
    author_email="zhouliang@shsmu.edu.cn",
    description="AI驱动的智能多视角质量校验引擎 — 26位视角专家全量扫描 + CI门禁 + 风险评分 + 增量diff + 基线对比",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/zhouliang-sjtu/iterative-qa",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: Healthcare Industry",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Scientific/Engineering :: Medical Science Apps",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "iterative-qa=iterative_qa.cli:main",
        ],
    },
    include_package_data=True,
    keywords=[
        "qa", "quality", "testing", "validation", "code-review",
        "ci-cd", "risk-scoring", "healthcare", "phi", "privacy",
        "llm", "ai", "devops", "security", "compliance",
    ],
)
