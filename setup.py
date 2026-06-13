"""iterative-qa - AI驱动的智能质量校验引擎"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="iterative-qa",
    version="3.0.0",
    author="周良",
    author_email="zhouliang@shsmu.edu.cn",
    description="AI驱动的智能多视角质量校验引擎 - 通过大模型分析项目特征，动态识别最优验证视角",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/zhouliang-sjtu/iterative-qa",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "iterative-qa=iterative_qa.cli:main",
        ],
    },
    include_package_data=True,
    keywords=["qa", "quality", "testing", "validation", "AI", "LLM"],
)