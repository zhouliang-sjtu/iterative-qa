"""项目扫描器 - 自动识别项目特征"""

import os
import re
from typing import Dict, List, Any

from .models import ProjectProfile


class ProjectScanner:
    """智能项目扫描器"""
    
    def __init__(self):
        # 技术栈特征映射
        self.tech_stack_patterns = {
            "Python": [r"\.py$"],
            "TypeScript": [r"\.ts$", r"\.tsx$"],
            "JavaScript": [r"\.js$", r"\.jsx$"],
            "React": ["react", "next"],
            "Vue": ["vue"],
            "FastAPI": ["fastapi"],
            "Django": ["django"],
            "SQLAlchemy": ["sqlalchemy"],
            "PostgreSQL": ["postgresql", "psycopg"],
            "Redis": ["redis"],
            "Docker": ["Dockerfile", "docker-compose"],
            "Node.js": ["package.json", "node_modules"],
            # Healthcare-specific libraries
            "FHIR": ["fhirclient", "fhiry", "fhir.resources"],
            "DICOM": ["pydicom", "dicom"],
            "HL7": ["hl7apy", "hl7"],
            "MedicalNLP": ["medspacy", "clinicalnlp", "scispacy"],
        }
        
        # 项目类型特征
        self.project_type_patterns = {
            "Web": ["frontend", "src", "public", "index.html"],
            "Mobile": ["android", "ios", "mobile"],
            "Desktop": ["electron", "desktop"],
            "Data": ["data", "pandas", "numpy", "spark"],
            "AI": ["tensorflow", "pytorch", "scikit-learn", "llm", "gpt"],
            "Backend": ["api", "backend", "server"],
            "Embedded": ["embedded", "firmware", "arduino"],
        }
        
        # 领域特征
        self.domain_patterns = {
            "金融": ["finance", "bank", "stock", "fund", "investment"],
            "医疗": [
                # English healthcare keywords
                "healthcare", "medical", "hospital", "patient", "clinic", "disease",
                "fhir", "hl7", "dicom", "hipaa", "phi", "ehr", "emr", "his",
                "clinical", "diagnosis", "prescription", "medicine", "pharmacy",
                "laboratory", "lab", "radiology", "pathology", "surgery",
                "vital_signs", "biometric", "observation", "encounter",
                # Chinese healthcare keywords
                "患者", "病历", "诊断", "处方", "药品", "医院", "临床",
                "检验", "检查", "影像", "病理", "手术", "体温", "血压", "血糖",
            ],
            "电商": ["ecommerce", "shop", "store", "product"],
            "教育": ["education", "learning", "course", "school"],
            "政府": ["government", "gov", "public"],
            "社交": ["social", "chat", "community"],
        }
    
    def scan(self, project_path: str) -> ProjectProfile:
        """扫描项目并提取特征"""
        features = self._extract_features(project_path)
        dynamic_features = self._detect_dynamic_analysis_features(project_path, features["files"])
        
        return ProjectProfile(
            project_type=features["project_type"],
            tech_stack=features["tech_stack"],
            complexity=features["complexity"],
            scale=features["scale"],
            domain=features["domain"],
            security_requirements=features["security_requirements"],
            file_count=features["file_count"],
            lines_of_code=features["lines_of_code"],
            # Dynamic analysis features
            has_database=dynamic_features["has_database"],
            database_type=dynamic_features["database_type"],
            database_url_available=dynamic_features["database_url_available"],
            has_api_framework=dynamic_features["has_api_framework"],
            has_openapi_schema=dynamic_features["has_openapi_schema"],
            api_endpoints_count=dynamic_features["api_endpoints_count"],
            service_running=dynamic_features["service_running"],
            service_port=dynamic_features["service_port"],
            has_sqlalchemy=dynamic_features["has_sqlalchemy"],
            has_orm_models=dynamic_features["has_orm_models"],
        )
    
    def _extract_features(self, project_path: str) -> Dict[str, Any]:
        """提取项目特征"""
        files = self._get_all_files(project_path)
        file_count = len(files)
        lines_of_code = self._count_lines(project_path)
        
        # 检测技术栈
        tech_stack = self._detect_tech_stack(files)
        
        # 检测项目类型
        project_type = self._detect_project_type(files)
        
        # 检测领域
        domain = self._detect_domain(files)
        
        # 评估规模和复杂度
        scale = self._estimate_scale(file_count, lines_of_code)
        complexity = self._estimate_complexity(file_count, lines_of_code, tech_stack)
        
        # 评估安全要求
        security_requirements = self._estimate_security_requirements(domain, project_type)
        
        return {
            "project_type": project_type,
            "tech_stack": tech_stack,
            "complexity": complexity,
            "scale": scale,
            "domain": domain,
            "security_requirements": security_requirements,
            "file_count": file_count,
            "lines_of_code": lines_of_code,
            "files": files,  # 新增：保留文件列表供后续动态分析
        }
    
    def _get_all_files(self, project_path: str) -> List[str]:
        """获取所有文件路径"""
        files = []
        for root, dirs, filenames in os.walk(project_path):
            # 排除一些目录
            dirs[:] = [d for d in dirs if d not in [
                '.git', 'node_modules', '__pycache__', 'venv', '.venv',
                'dist', 'build', 'output', 'logs'
            ]]
            
            for filename in filenames:
                files.append(os.path.join(root, filename))
        
        return files
    
    def _count_lines(self, project_path: str) -> int:
        """计算代码行数"""
        lines = 0
        for root, dirs, filenames in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in [
                '.git', 'node_modules', '__pycache__', 'venv', '.venv'
            ]]
            
            for filename in filenames:
                if filename.endswith(('.py', '.ts', '.tsx', '.js', '.jsx')):
                    try:
                        with open(os.path.join(root, filename), 'r', encoding='utf-8', errors='ignore') as f:
                            lines += len(f.readlines())
                    except:
                        pass
        
        return lines
    
    def _detect_tech_stack(self, files: List[str]) -> List[str]:
        """检测技术栈"""
        detected = []
        
        for tech, patterns in self.tech_stack_patterns.items():
            for pattern in patterns:
                for filepath in files:
                    filename = os.path.basename(filepath).lower()
                    content = ""
                    
                    # 检查文件名
                    if re.search(pattern.lower(), filename):
                        detected.append(tech)
                        break
                    
                    # 检查文件内容（对于配置文件）
                    if filename in ['package.json', 'requirements.txt', 'pyproject.toml']:
                        try:
                            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read().lower()
                                if pattern.lower() in content:
                                    detected.append(tech)
                                    break
                        except:
                            pass
            
            if tech in detected:
                continue
        
        return sorted(list(set(detected)))
    
    def _detect_project_type(self, files: List[str]) -> str:
        """检测项目类型"""
        for project_type, patterns in self.project_type_patterns.items():
            for pattern in patterns:
                pattern_lower = pattern.lower()
                for filepath in files:
                    path_lower = filepath.lower()
                    if pattern_lower in path_lower:
                        return project_type
        
        # 默认返回Web
        return "Web"
    
    def _detect_domain(self, files: List[str]) -> str:
        """检测业务领域"""
        for domain, keywords in self.domain_patterns.items():
            for keyword in keywords:
                keyword_lower = keyword.lower()
                for filepath in files:
                    filename = os.path.basename(filepath).lower()
                    if keyword_lower in filename:
                        return domain
                    
                    # 检查文件内容（README, docs）
                    if filename in ['readme.md', 'readme.txt', 'docs']:
                        try:
                            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read().lower()
                                if keyword_lower in content:
                                    return domain
                        except:
                            pass
        
        return "通用"
    
    def _estimate_scale(self, file_count: int, lines_of_code: int) -> str:
        """评估项目规模"""
        if lines_of_code > 100000 or file_count > 500:
            return "enterprise"
        elif lines_of_code > 10000 or file_count > 100:
            return "large"
        elif lines_of_code > 1000 or file_count > 20:
            return "medium"
        else:
            return "small"
    
    def _estimate_complexity(self, file_count: int, lines_of_code: int, tech_stack: List[str]) -> str:
        """评估项目复杂度"""
        complexity_score = 0
        
        # 基于代码量
        if lines_of_code > 50000:
            complexity_score += 3
        elif lines_of_code > 10000:
            complexity_score += 2
        elif lines_of_code > 1000:
            complexity_score += 1
        
        # 基于技术栈复杂度
        complex_techs = ["AI", "Data", "Embedded", "Docker"]
        for tech in tech_stack:
            if tech in complex_techs:
                complexity_score += 1
        
        # 基于文件数量
        if file_count > 200:
            complexity_score += 2
        elif file_count > 50:
            complexity_score += 1
        
        if complexity_score >= 5:
            return "high"
        elif complexity_score >= 3:
            return "medium"
        else:
            return "low"
    
    def _estimate_security_requirements(self, domain: str, project_type: str) -> int:
        """评估安全要求等级"""
        score = 5  # 默认中等
        
        # 领域因素
        high_security_domains = ["金融", "医疗", "政府"]
        if domain in high_security_domains:
            score += 3
        
        # 项目类型因素
        if project_type in ["Web", "Mobile"]:
            score += 1
        
        return min(10, max(1, score))
    
    def _detect_dynamic_analysis_features(self, project_path: str, files: List[str]) -> Dict[str, Any]:
        """检测动态分析相关特征（数据库、API框架、服务状态等）"""
        features = {
            "has_database": False,
            "database_type": "",
            "database_url_available": False,
            "has_api_framework": False,
            "has_openapi_schema": False,
            "api_endpoints_count": 0,
            "service_running": False,
            "service_port": 0,
            "has_sqlalchemy": False,
            "has_orm_models": False,
        }
        
        # ─── 1. 检测数据库配置 ────────────────────────────────────────────
        db_patterns = {
            "postgresql": ["postgresql", "postgres", "psycopg"],
            "mysql": ["mysql", "mysqldb", "pymysql"],
            "sqlite": ["sqlite", "sqlite3"],
            "mongodb": ["mongodb", "mongo", "pymongo"],
        }
        
        # 检查 .env 文件和配置文件
        env_files = [f for f in files if f.endswith('.env') or '.env.' in os.path.basename(f)]
        config_files = [f for f in files if os.path.basename(f) in ['config.py', 'settings.py', 'config.yaml', 'config.json']]
        
        for filepath in env_files + config_files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                    if 'database_url' in content or 'db_url' in content:
                        features["has_database"] = True
                        features["database_url_available"] = True
                        for db_type, patterns in db_patterns.items():
                            if any(p in content for p in patterns):
                                features["database_type"] = db_type
                                break
            except:
                pass
        
        # 检查 requirements.txt / pyproject.toml
        dep_files = [f for f in files if os.path.basename(f) in ['requirements.txt', 'pyproject.toml', 'setup.py']]
        for filepath in dep_files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                    if 'sqlalchemy' in content:
                        features["has_sqlalchemy"] = True
                        features["has_database"] = True
                    if not features["database_type"]:
                        for db_type, patterns in db_patterns.items():
                            if any(p in content for p in patterns):
                                features["database_type"] = db_type
                                break
            except:
                pass
        
        # ─── 2. 检测 ORM Model 定义 ────────────────────────────────────────
        model_files = [f for f in files if 'model' in f.lower() and f.endswith('.py')]
        for filepath in model_files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    # 检测 SQLAlchemy Model 定义
                    if re.search(r'class\s+\w+\s*\(\s*Base\s*\)', content) or \
                       re.search(r'\bColumn\s*\(', content) or \
                       re.search(r'\bdeclarative_base\b', content):
                        features["has_orm_models"] = True
                        features["has_sqlalchemy"] = True
                        break
            except:
                pass
        
        # ─── 3. 检测 API 框架 ──────────────────────────────────────────────
        api_patterns = {
            "FastAPI": ["fastapi", "from fastapi import", "APIRouter", "@app.get", "@app.post"],
            "Flask": ["flask", "from flask import", "@app.route"],
            "DjangoREST": ["django", "rest_framework", "APIView", "serializers"],
        }
        
        py_files = [f for f in files if f.endswith('.py')]
        endpoint_count = 0
        
        for filepath in py_files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    for api_name, patterns in api_patterns.items():
                        if any(p in content for p in patterns):
                            features["has_api_framework"] = True
                            break
                    # 统计端点数量
                    endpoint_count += len(re.findall(r'@(app|router)\.(get|post|put|delete|patch)\s*\(', content))
                    endpoint_count += len(re.findall(r'@app\.route\s*\(', content))
            except:
                pass
        
        features["api_endpoints_count"] = endpoint_count
        
        # ─── 4. 检测 OpenAPI Schema ────────────────────────────────────────
        openapi_files = [f for f in files if 'openapi' in f.lower() or f.endswith('.json')]
        for filepath in openapi_files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if '"openapi"' in content or '"paths"' in content:
                        features["has_openapi_schema"] = True
                        break
            except:
                pass
        
        # ─── 5. 检测服务运行状态 ───────────────────────────────────────────
        # 尝试探测常见端口
        common_ports = [8000, 5000, 3000, 8080, 8888]
        import socket
        for port in common_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex(('localhost', port))
                if result == 0:
                    features["service_running"] = True
                    features["service_port"] = port
                    break
                sock.close()
            except:
                pass
        
        return features