"""iterative-qa - AI驱动的智能质量校验引擎"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="iterative-qa",
    version="3.0.0",
    author="您的姓名",
    author_email="your@email.com",
    description="AI驱动的智能多视角质量校验引擎",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/iterative-qa",
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
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "iterative-qa=iterative_qa.cli:main",
        ],
    },
    include_package_data=True,
    keywords=["qa", "quality", "testing", "validation", "AI", "LLM"],
)