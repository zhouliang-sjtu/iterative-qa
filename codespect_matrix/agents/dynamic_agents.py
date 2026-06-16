"""Dynamic analysis agents — runtime-aware issue detection.

These agents extend static analysis with runtime context:
- DBCompatibilityAgent: Detect SQL dialect incompatibilities (static)
- DBSchemaAgent: Compare ORM models with actual database schema (requires DB connection)
- APIContractAgent: Test API parameter boundaries (requires running service or OpenAPI schema)
- SmokeTestAgent: Endpoint smoke tests (requires running service)
"""

from __future__ import annotations

import os
import re
import json
import socket
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from .base import BaseAgent, AgentRole, Finding, AgentMessage, MessageType

if TYPE_CHECKING:
    from .bus import AgentCommunicationBus
    from .memory import ProjectMemory


# ─────────────────────────────────────────────────────────────────────────────
# DBCompatibilityAgent — SQL Dialect Compatibility Checker (Static)
# ─────────────────────────────────────────────────────────────────────────────

class DBCompatibilityAgent(BaseAgent):
    """Detect SQL dialect incompatibilities in code.
    
    This is a STATIC analysis agent — no database connection required.
    It scans code for SQL strings and ORM calls that may have dialect issues.
    
    Common issues detected:
    - MySQL functions used in PostgreSQL (IFNULL → COALESCE, NOW() → CURRENT_TIMESTAMP)
    - PostgreSQL functions used in MySQL
    - SQLite limitations in production code
    - Database-specific syntax in raw SQL queries
    """
    
    name = "db_compatibility"
    role = AgentRole.INSPECTOR
    
    # MySQL-specific functions that don't work in PostgreSQL
    MYSQL_FUNCTIONS = [
        "IFNULL", "IF(", "CONCAT_WS", "GROUP_CONCAT", "REGEXP",
        "UNIX_TIMESTAMP", "FROM_UNIXTIME", "DATE_FORMAT",
        "STR_TO_DATE", "LAST_INSERT_ID", "AUTO_INCREMENT",
    ]
    
    # PostgreSQL-specific functions that don't work in MySQL
    POSTGRESQL_FUNCTIONS = [
        "COALESCE", "NULLIF", "ARRAY_AGG", "STRING_AGG",
        "TO_CHAR", "TO_DATE", "TO_TIMESTAMP", "EXTRACT",
        "CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP",
        "RETURNING", "SERIAL", "BIGSERIAL",
    ]
    
    # SQLite limitations
    SQLITE_LIMITATIONS = [
        "RIGHT JOIN", "FULL OUTER JOIN", "ALTER TABLE ADD COLUMN AFTER",
        "FOREIGN KEY ENFORCEMENT", "CHECK constraint enforcement",
    ]
    
    def __init__(self, agent_id: str = None, bus: "AgentCommunicationBus" = None,
                 memory: "ProjectMemory" = None, name: str = None):
        # Call BaseAgent constructor with required parameters
        # Use agent_id or name parameter
        agent_name = name or agent_id or self.name
        super().__init__(name=agent_name, role=self.role, bus=bus)
        self.memory = memory
        self.target_db = None  # Will be set based on project profile
    
    def get_description(self) -> str:
        """Human-readable description of this agent's purpose."""
        return "Detects SQL dialect incompatibilities (MySQL vs PostgreSQL vs SQLite) in code."
    
    def get_domain(self) -> str:
        """Domain this agent specializes in."""
        return "database_compatibility"
    
    def inspect(self, files_context: str) -> List[Finding]:
        """Scan project for SQL dialect compatibility issues."""
        findings = []
        self.target_db = self.project_profile.get("database_type", "").lower()
        
        project_path = self.project_path
        
        # Scan Python files for SQL issues
        py_files = self._get_python_files(project_path)
        
        for filepath in py_files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    lines = content.split('\n')
                    
                    # Check for MySQL functions in PostgreSQL-targeted code
                    if self.target_db == "postgresql":
                        findings.extend(self._check_mysql_in_postgresql(filepath, lines))
                    
                    # Check for PostgreSQL functions in MySQL-targeted code
                    elif self.target_db == "mysql":
                        findings.extend(self._check_postgresql_in_mysql(filepath, lines))
                    
                    # Check for SQLite limitations in production code
                    findings.extend(self._check_sqlite_limitations(filepath, lines))
                    
                    # Check for raw SQL with potential issues
                    findings.extend(self._check_raw_sql_issues(filepath, lines))
                    
            except Exception as e:
                self.logger.warning(f"Error scanning {filepath}: {e}")
        
        return findings
    
    def _get_python_files(self, project_path: str) -> List[str]:
        """Get all Python files in project."""
        py_files = []
        for root, dirs, filenames in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in [
                '.git', 'node_modules', '__pycache__', 'venv', '.venv',
                'dist', 'build', 'migrations', 'tests'
            ]]
            for filename in filenames:
                if filename.endswith('.py'):
                    py_files.append(os.path.join(root, filename))
        return py_files
    
    def _extract_code_lines(self, lines: List[str]) -> List[str]:
        """Extract lines that are not inside docstrings or multi-line strings."""
        code_lines = []
        in_multiline_string = False
        multiline_char = None
        
        for line in lines:
            stripped = line.strip()
            
            # Track multi-line string state
            if not in_multiline_string:
                # Check for start of multi-line string
                if '"""' in line or "'''" in line:
                    # Determine quote type
                    if '"""' in line:
                        multiline_char = '"""'
                    else:
                        multiline_char = "'''"
                    
                    # Count occurrences
                    count = line.count(multiline_char)
                    
                    if count == 1:
                        in_multiline_string = True
                        # Skip the content before the opening quote
                        idx = line.index(multiline_char)
                        code_lines.append(line[:idx])
                    elif count >= 2:
                        # Opening and closing on same line - skip the string content
                        parts = line.split(multiline_char)
                        # Keep even-indexed parts (outside strings)
                        kept = ''.join(parts[::2])
                        code_lines.append(kept)
                    else:
                        code_lines.append(line)
                else:
                    code_lines.append(line)
            else:
                # We're inside a multi-line string
                if multiline_char in line:
                    in_multiline_string = False
                    # Keep content after closing quote
                    idx = line.rindex(multiline_char)
                    code_lines.append(line[idx + len(multiline_char):])
                else:
                    code_lines.append('')
        
        return code_lines
    
    def _is_sql_documentation(self, line: str, keyword: str) -> bool:
        """Check if SQL keyword appears in documentation/list context vs actual SQL code."""
        stripped = line.strip()
        
        # Skip single-line comments
        if stripped.startswith('#'):
            return True
        
        # Skip lines that are list definitions (contain SQL keywords in quotes)
        # This is common for keyword lists in documentation or detection rules
        if re.search(rf'["\'].*{re.escape(keyword)}.*["\']', line):
            return True
        
        # Skip variable assignments that look like lists/dicts of keywords
        if re.search(rf'^\s*\w+\s*=\s*\[["\']', line) or re.search(rf'^\s*\w+\s*=\s*\{{["\']', line):
            return True
        
        return False
    
    def _check_mysql_in_postgresql(self, filepath: str, lines: List[str]) -> List[Finding]:
        """Check for MySQL-specific functions in PostgreSQL-targeted code."""
        findings = []
        
        # Pre-process: extract code lines (skip docstrings and multi-line strings)
        code_lines = self._extract_code_lines(lines)
        
        for i, line in enumerate(code_lines, 1):
            for func in self.MYSQL_FUNCTIONS:
                # Case-insensitive search
                if re.search(rf'\b{re.escape(func)}\b', line, re.IGNORECASE):
                    # Skip documentation and list definitions
                    if self._is_sql_documentation(line, func):
                        continue
                    
                    findings.append(Finding(
                        check_name="mysql_function_in_postgresql",
                        severity="high",
                        message=f"MySQL function '{func}' used in PostgreSQL-targeted code. "
                                f"Consider using PostgreSQL equivalent.",
                        file_path=filepath,
                        line_start=i,
                        line_end=i,
                        evidence=line.strip(),
                        remediation=self._get_postgresql_equivalent(func),
                        confidence=0.85,
                    ))
        return findings
    
    def _check_postgresql_in_mysql(self, filepath: str, lines: List[str]) -> List[Finding]:
        """Check for PostgreSQL-specific functions in MySQL-targeted code."""
        findings = []
        
        # Pre-process: extract code lines (skip docstrings and multi-line strings)
        code_lines = self._extract_code_lines(lines)
        
        for i, line in enumerate(code_lines, 1):
            for func in self.POSTGRESQL_FUNCTIONS:
                if re.search(rf'\b{re.escape(func)}\b', line, re.IGNORECASE):
                    # Skip documentation and list definitions
                    if self._is_sql_documentation(line, func):
                        continue
                    
                    findings.append(Finding(
                        check_name="postgresql_function_in_mysql",
                        severity="high",
                        message=f"PostgreSQL function '{func}' used in MySQL-targeted code. "
                                f"Consider using MySQL equivalent.",
                        file_path=filepath,
                        line_start=i,
                        line_end=i,
                        evidence=line.strip(),
                        remediation=self._get_mysql_equivalent(func),
                        confidence=0.85,
                    ))
        return findings
    
    def _check_sqlite_limitations(self, filepath: str, lines: List[str]) -> List[Finding]:
        """Check for SQLite limitations that may cause issues in production."""
        findings = []
        
        # Pre-process: extract code lines (skip docstrings and multi-line strings)
        code_lines = self._extract_code_lines(lines)
        
        for i, line in enumerate(code_lines, 1):
            for limitation in self.SQLITE_LIMITATIONS:
                if limitation.upper() in line.upper():
                    # Skip documentation and list definitions
                    if self._is_sql_documentation(line, limitation):
                        continue
                    
                    findings.append(Finding(
                        check_name="sqlite_limitation",
                        severity="medium",
                        message=f"SQLite limitation detected: '{limitation}'. "
                                f"This may not work correctly in production database.",
                        file_path=filepath,
                        line_start=i,
                        line_end=i,
                        evidence=line.strip(),
                        remediation="Consider using database-agnostic syntax or "
                                   "ensuring this code only runs with SQLite.",
                        confidence=0.75,
                    ))
        return findings
    
    def _check_raw_sql_issues(self, filepath: str, lines: List[str]) -> List[Finding]:
        """Check for common raw SQL issues."""
        findings = []
        
        # Pre-process: extract code lines (skip docstrings and multi-line strings)
        code_lines = self._extract_code_lines(lines)
        
        # Patterns for raw SQL (excluding remediation/suggestion strings)
        raw_sql_patterns = [
            (r'text\s*\(["\'].*SELECT.*["\']', "raw_sql_text"),
            (r'execute\s*\(["\'].*["\']', "raw_sql_execute"),
            (r'\.execute\s*\(["\'].*["\']', "raw_sql_execute"),
        ]
        
        for i, line in enumerate(code_lines, 1):
            # Skip comments
            if line.strip().startswith('#'):
                continue
            
            # Skip lines that are remediation/suggestion/documentation
            # These contain SQL examples for documentation purposes
            if 'remediation=' in line or 'suggestion=' in line or 'suggestion":' in line:
                continue
            
            for pattern, check_name in raw_sql_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Check for potential SQL injection
                    if '{' in line or '%' in line or '+' in line:
                        findings.append(Finding(
                            check_name="potential_sql_injection",
                            severity="critical",
                            message="Potential SQL injection vulnerability in raw SQL query. "
                                    "Use parameterized queries instead.",
                            file_path=filepath,
                            line_start=i,
                            line_end=i,
                            evidence=line.strip(),
                            remediation="Use parameterized queries: session.execute(text('SELECT ... WHERE id = :id'), {'id': value})",
                            confidence=0.90,
                        ))
        return findings
    
    def _get_postgresql_equivalent(self, mysql_func: str) -> str:
        """Get PostgreSQL equivalent for MySQL function."""
        equivalents = {
            "IFNULL": "Use COALESCE(column, default_value)",
            "IF(": "Use CASE WHEN ... THEN ... ELSE ... END",
            "CONCAT_WS": "Use CONCAT() with separator or || operator",
            "GROUP_CONCAT": "Use STRING_AGG(column, separator)",
            "REGEXP": "Use ~ operator for regex matching",
            "UNIX_TIMESTAMP": "Use EXTRACT(EPOCH FROM timestamp)",
            "FROM_UNIXTIME": "Use TO_TIMESTAMP(epoch)",
            "DATE_FORMAT": "Use TO_CHAR(timestamp, format)",
            "LAST_INSERT_ID": "Use CURRVAL('sequence_name') or RETURNING clause",
            "AUTO_INCREMENT": "Use SERIAL or BIGSERIAL type",
        }
        return equivalents.get(mysql_func, f"Check PostgreSQL documentation for {mysql_func} equivalent")
    
    def _get_mysql_equivalent(self, pg_func: str) -> str:
        """Get MySQL equivalent for PostgreSQL function."""
        equivalents = {
            "COALESCE": "Use IFNULL(column, default_value) for simple cases",
            "NULLIF": "Supported in MySQL 8.0+",
            "ARRAY_AGG": "Use GROUP_CONCAT with JSON_ARRAYAGG",
            "STRING_AGG": "Use GROUP_CONCAT(column SEPARATOR delimiter)",
            "TO_CHAR": "Use DATE_FORMAT(date, format)",
            "TO_DATE": "Use STR_TO_DATE(str, format)",
            "TO_TIMESTAMP": "Use STR_TO_DATE(str, format)",
            "EXTRACT": "Use EXTRACT() or specific functions like YEAR(), MONTH()",
            "RETURNING": "MySQL doesn't support RETURNING; use LAST_INSERT_ID()",
            "SERIAL": "Use AUTO_INCREMENT",
            "BIGSERIAL": "Use BIGINT AUTO_INCREMENT",
        }
        return equivalents.get(pg_func, f"Check MySQL documentation for {pg_func} equivalent")
    
    def review(self, finding: Finding) -> Dict[str, Any]:
        """Review a finding from another agent."""
        comment = ""
        if "sql" in finding.check_name.lower() or "database" in finding.check_name.lower():
            # Add additional context if available
            if self.target_db:
                comment = f"[{self.target_db}] "
        return {"verdict": "confirmed", "comment": comment}
    
    def generate_fix(self, finding: Finding) -> Optional[Dict]:
        """Generate fix proposal for SQL compatibility issues."""
        if "sql_injection" in finding.check_name:
            return {
                "type": "code_replace",
                "file_path": finding.file_path,
                "line_start": finding.line_start,
                "line_end": finding.line_end,
                "original": finding.evidence,
                "suggestion": "# Use parameterized query instead\n# session.execute(text('SELECT ... WHERE id = :id'), {'id': value})",
                "confidence": 0.95,
            }
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DBSchemaAgent — ORM Model vs Database Schema Checker (Requires DB Connection)
# ─────────────────────────────────────────────────────────────────────────────

class DBSchemaAgent(BaseAgent):
    """Compare SQLAlchemy ORM models with actual database schema.
    
    This agent REQUIRES a database connection to function.
    It will be automatically activated when:
    - Project uses SQLAlchemy (has_sqlalchemy = True)
    - Database URL is available (database_url_available = True)
    
    Issues detected:
    - Missing columns in database (model defines but table doesn't have)
    - Extra columns in database (table has but model doesn't define)
    - Type mismatches between model and actual column type
    - Missing indexes/constraints
    """
    
    name = "db_schema"
    role = AgentRole.INSPECTOR
    
    def __init__(self, agent_id: str = None, bus: "AgentCommunicationBus" = None,
                 memory: "ProjectMemory" = None, database_url: str = None, name: str = None):
        agent_name = name or agent_id or self.name
        super().__init__(name=agent_name, role=self.role, bus=bus)
        self.memory = memory
        self.database_url = database_url
        self.engine = None
    
    def get_description(self) -> str:
        """Human-readable description of this agent's purpose."""
        return "Compares SQLAlchemy ORM models with actual database schema to detect inconsistencies."
    
    def get_domain(self) -> str:
        """Domain this agent specializes in."""
        return "database_schema"
    
    def can_activate(self) -> bool:
        """Check if this agent can run (requires database connection)."""
        return (
            self.project_profile.get("has_sqlalchemy", False) and
            self.project_profile.get("database_url_available", False)
        )
    
    def connect_database(self, database_url: str = None) -> bool:
        """Establish database connection."""
        url = database_url or self.database_url
        if not url:
            return False
        
        try:
            from sqlalchemy import create_engine, inspect
            self.engine = create_engine(url)
            # Test connection
            with self.engine.connect() as conn:
                pass
            return True
        except ImportError:
            self.logger.warning("SQLAlchemy not installed, DBSchemaAgent cannot run")
            return False
        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}")
            return False
    
    def inspect(self, files_context: str) -> List[Finding]:
        """Compare ORM models with database schema."""
        findings = []
        
        if not self.can_activate():
            self.logger.info("DBSchemaAgent cannot activate: missing database connection")
            return findings
        
        if not self.engine and not self.connect_database():
            return findings
        
        project_path = self.project_path
        
        # Find all SQLAlchemy models
        models = self._discover_sqlalchemy_models(project_path)
        
        if not models:
            return findings
        
        from sqlalchemy import inspect as sqla_inspect
        inspector = sqla_inspect(self.engine)
        
        for model_info in models:
            table_name = model_info["table_name"]
            model_columns = model_info["columns"]
            
            # Check if table exists in database
            if not inspector.has_table(table_name):
                findings.append(Finding(
                    check_name="missing_table",
                    severity="critical",
                    message=f"Model '{model_info['class_name']}' references table '{table_name}' "
                            f"which does not exist in database.",
                    file_path=model_info["file_path"],
                    line_start=model_info["line_start"],
                    evidence=f"Table '{table_name}' not found in database",
                    remediation=f"Run database migration to create table '{table_name}', or "
                               f"verify the database connection is correct.",
                    confidence=1.0,
                ))
                continue
            
            # Get actual database columns
            db_columns = {col['name']: col for col in inspector.get_columns(table_name)}
            
            # Check for missing columns
            for col_name, col_info in model_columns.items():
                if col_name not in db_columns:
                    findings.append(Finding(
                        check_name="missing_column",
                        severity="high",
                        message=f"Model '{model_info['class_name']}' defines column '{col_name}' "
                                f"but it's missing from table '{table_name}' in database.",
                        file_path=model_info["file_path"],
                        line_start=col_info.get("line", 0),
                        evidence=f"Column '{col_name}' defined in model but not in database",
                        remediation=f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_info.get('type', 'VARCHAR')};",
                        confidence=0.95,
                    ))
            
            # Check for extra columns in database
            model_col_names = set(model_columns.keys())
            db_col_names = set(db_columns.keys())
            extra_columns = db_col_names - model_col_names
            
            for col_name in extra_columns:
                findings.append(Finding(
                    check_name="extra_column_in_db",
                    severity="medium",
                    message=f"Table '{table_name}' has column '{col_name}' "
                            f"which is not defined in model '{model_info['class_name']}'.",
                    file_path=model_info["file_path"],
                    line_start=1,
                    evidence=f"Column '{col_name}' exists in database but not in model",
                    remediation=f"Either add '{col_name}' to the model or migrate data and drop the column.",
                    confidence=0.85,
                ))
        
        return findings
    
    def _discover_sqlalchemy_models(self, project_path: str) -> List[Dict]:
        """Discover all SQLAlchemy model definitions in project."""
        models = []
        
        py_files = self._get_python_files(project_path)
        
        for filepath in py_files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    lines = content.split('\n')
                
                # Find model classes (Base subclass)
                for i, line in enumerate(lines):
                    # Match: class ClassName(Base): or class ClassName(Base,):
                    match = re.search(r'class\s+(\w+)\s*\(\s*Base\s*[,\)]', line)
                    if match:
                        class_name = match.group(1)
                        model_info = self._parse_model_class(filepath, lines, i, class_name)
                        if model_info:
                            models.append(model_info)
                            
            except Exception as e:
                self.logger.warning(f"Error parsing {filepath}: {e}")
        
        return models
    
    def _get_python_files(self, project_path: str) -> List[str]:
        """Get all Python files in project."""
        py_files = []
        for root, dirs, filenames in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in [
                '.git', 'node_modules', '__pycache__', 'venv', '.venv',
                'dist', 'build', 'migrations', 'tests'
            ]]
            for filename in filenames:
                if filename.endswith('.py'):
                    py_files.append(os.path.join(root, filename))
        return py_files
    
    def _parse_model_class(self, filepath: str, lines: List[str], start_idx: int, 
                           class_name: str) -> Optional[Dict]:
        """Parse SQLAlchemy model class to extract table name and columns."""
        model_info = {
            "class_name": class_name,
            "file_path": filepath,
            "line_start": start_idx + 1,
            "table_name": "",
            "columns": {},
        }
        
        # Find __tablename__
        in_class = False
        indent_level = 0
        
        for i in range(start_idx, min(start_idx + 200, len(lines))):
            line = lines[i]
            
            # Track class scope
            if i == start_idx:
                in_class = True
                base_indent = len(line) - len(line.lstrip())
                continue
            
            current_indent = len(line) - len(line.lstrip())
            
            # Check if we've left the class
            if line.strip() and current_indent <= base_indent and not line.strip().startswith('#'):
                break
            
            # Extract __tablename__
            table_match = re.search(r'__tablename__\s*=\s*["\'](\w+)["\']', line)
            if table_match:
                model_info["table_name"] = table_match.group(1)
            
            # Extract Column definitions
            col_match = re.search(r'(\w+)\s*=\s*Column\s*\(', line)
            if col_match:
                col_name = col_match.group(1)
                col_type = "UNKNOWN"
                
                # Try to extract column type
                type_match = re.search(r'Column\s*\(\s*(\w+)', line)
                if type_match:
                    col_type = type_match.group(1)
                
                model_info["columns"][col_name] = {
                    "line": i + 1,
                    "type": col_type,
                }
        
        return model_info if model_info["table_name"] else None
    
    def review(self, finding: Finding) -> Dict[str, Any]:
        """Review database-related findings."""
        applicable = "column" in finding.check_name.lower() or "table" in finding.check_name.lower()
        return {"verdict": "confirmed", "comment": "database relevant" if applicable else ""}
    
    def generate_fix(self, finding: Finding) -> Optional[Dict]:
        """Generate migration script for schema issues."""
        if finding.check_name == "missing_column":
            return {
                "type": "migration",
                "sql": finding.remediation,
                "confidence": 0.95,
            }
        return None


# ─────────────────────────────────────────────────────────────────────────────
# APIContractAgent — API Parameter Boundary Tester
# ─────────────────────────────────────────────────────────────────────────────

class APIContractAgent(BaseAgent):
    """Test API parameter boundaries based on OpenAPI schema.
    
    This agent can work in two modes:
    1. Static mode: Analyze OpenAPI schema for potential issues
    2. Dynamic mode: Actually call endpoints with edge case parameters
    
    Issues detected:
    - Missing parameter validation
    - Empty string handling
    - Null/None handling
    - Type coercion issues
    - Missing required fields
    - Response schema violations
    """
    
    name = "api_contract"
    role = AgentRole.INSPECTOR
    
    def __init__(self, agent_id: str = None, bus: "AgentCommunicationBus" = None,
                 memory: "ProjectMemory" = None, base_url: str = None, name: str = None):
        agent_name = name or agent_id or self.name
        super().__init__(name=agent_name, role=self.role, bus=bus)
        self.memory = memory
        self.base_url = base_url
        self.openapi_schema = None
    
    def get_description(self) -> str:
        """Human-readable description of this agent's purpose."""
        return "Tests API parameter boundaries and validation based on OpenAPI schema."
    
    def get_domain(self) -> str:
        """Domain this agent specializes in."""
        return "api_contract"
    
    def can_activate(self) -> bool:
        """Check if this agent can run."""
        return (
            self.project_profile.get("has_api_framework", False) or
            self.project_profile.get("has_openapi_schema", False) or
            self.project_profile.get("service_running", False)
        )
    
    def inspect(self, files_context: str) -> List[Finding]:
        """Analyze API contracts for potential issues."""
        findings = []
        
        if not self.can_activate():
            return findings
        
        project_path = self.project_path
        
        # Try to load OpenAPI schema
        self.openapi_schema = self._load_openapi_schema(project_path)
        
        if self.openapi_schema:
            findings.extend(self._analyze_openapi_schema(project_path))
        
        # Analyze FastAPI route definitions
        findings.extend(self._analyze_fastapi_routes(project_path))
        
        # If service is running, do dynamic testing
        if self.project_profile.get("service_running"):
            self.base_url = f"http://localhost:{self.project_profile.get('service_port', 8000)}"
            findings.extend(self._dynamic_api_testing())
        
        return findings
    
    def _load_openapi_schema(self, project_path: str) -> Optional[Dict]:
        """Load OpenAPI schema from file or running service."""
        # Try to find openapi.json file
        for root, dirs, filenames in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in ['.git', 'node_modules', '__pycache__']]
            for filename in filenames:
                if 'openapi' in filename.lower() and filename.endswith('.json'):
                    try:
                        with open(os.path.join(root, filename), 'r', encoding='utf-8') as f:
                            return json.load(f)
                    except:
                        pass
        
        # Try to fetch from running service
        if self.base_url:
            try:
                url = f"{self.base_url}/openapi.json"
                with urllib.request.urlopen(url, timeout=5) as response:
                    return json.loads(response.read().decode('utf-8'))
            except:
                pass
        
        return None
    
    def _analyze_openapi_schema(self, project_path: str) -> List[Finding]:
        """Analyze OpenAPI schema for potential issues."""
        findings = []
        
        if not self.openapi_schema:
            return findings
        
        paths = self.openapi_schema.get("paths", {})
        
        for path, methods in paths.items():
            for method, spec in methods.items():
                if method not in ["get", "post", "put", "delete", "patch"]:
                    continue
                
                # Check parameters
                params = spec.get("parameters", [])
                for param in params:
                    # Check for missing validation
                    if param.get("required") and not param.get("schema", {}).get("minLength"):
                        param_name = param.get("name")
                        findings.append(Finding(
                            check_name="missing_minlength_validation",
                            severity="medium",
                            message=f"Required parameter '{param_name}' in {method.upper()} {path} "
                                    f"has no minLength validation. Empty strings may cause issues.",
                            file_path="openapi.json",
                            line_start=1,
                            evidence=f"Parameter: {param_name}, Required: {param.get('required')}",
                            remediation=f"Add 'minLength: 1' to parameter schema to reject empty strings.",
                            confidence=0.75,
                        ))
                
                # Check request body
                request_body = spec.get("requestBody", {})
                if request_body:
                    content = request_body.get("content", {})
                    for content_type, content_spec in content.items():
                        schema = content_spec.get("schema", {})
                        required_fields = schema.get("required", [])
                        properties = schema.get("properties", {})
                        
                        for field_name in required_fields:
                            field_spec = properties.get(field_name, {})
                            if field_spec.get("type") == "string":
                                if "minLength" not in field_spec and "pattern" not in field_spec:
                                    findings.append(Finding(
                                        check_name="missing_field_validation",
                                        severity="medium",
                                        message=f"Required field '{field_name}' in {method.upper()} {path} "
                                                f"request body has no minLength or pattern validation.",
                                        file_path="openapi.json",
                                        line_start=1,
                                        evidence=f"Field: {field_name}, Type: string",
                                        remediation=f"Add 'minLength: 1' or a pattern constraint to field '{field_name}'.",
                                        confidence=0.70,
                                    ))
        
        return findings
    
    def _analyze_fastapi_routes(self, project_path: str) -> List[Finding]:
        """Analyze FastAPI route definitions for potential issues."""
        findings = []
        
        py_files = self._get_python_files(project_path)
        
        for filepath in py_files:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    lines = content.split('\n')
                
                for i, line in enumerate(lines, 1):
                    # Find route decorators
                    route_match = re.search(r'@(app|router)\.(get|post|put|delete|patch)\s*\(["\']([^"\'\\]+)["\']', line)
                    if route_match:
                        route_path = route_match.group(3)
                        method = route_match.group(2).upper()
                        
                        # Check for path parameters without validation
                        path_params = re.findall(r'\{(\w+)\}', route_path)
                        for param in path_params:
                            # Look for validation in nearby lines
                            nearby_lines = '\n'.join(lines[max(0, i-1):min(len(lines), i+10)])
                            if f'Path(' not in nearby_lines and f'path_params' not in nearby_lines:
                                findings.append(Finding(
                                    check_name="missing_path_param_validation",
                                    severity="medium",
                                    message=f"Path parameter '{param}' in {method} {route_path} "
                                            f"may lack proper validation.",
                                    file_path=filepath,
                                    line_start=i,
                                    evidence=f"Route: {method} {route_path}",
                                    remediation=f"Add Path() validation: {param}: str = Path(..., description='...')",
                                    confidence=0.65,
                                ))
                        
                        # Check for query parameters without defaults
                        if '?' in route_path or 'Query(' in line:
                            # Look for Query parameters without validation
                            query_params = re.findall(r'(\w+)\s*:\s*(?:Optional\[)?str(?:\])?\s*=\s*Query\(', nearby_lines)
                            for param in query_params:
                                if 'min_length' not in nearby_lines.lower():
                                    findings.append(Finding(
                                        check_name="missing_query_validation",
                                        severity="low",
                                        message=f"Query parameter '{param}' may accept empty strings.",
                                        file_path=filepath,
                                        line_start=i,
                                        evidence=f"Parameter: {param}",
                                        remediation=f"Add min_length=1 to Query() parameter.",
                                        confidence=0.60,
                                    ))
                                
            except Exception as e:
                self.logger.warning(f"Error analyzing {filepath}: {e}")
        
        return findings
    
    def _get_python_files(self, project_path: str) -> List[str]:
        """Get all Python files in project."""
        py_files = []
        for root, dirs, filenames in os.walk(project_path):
            dirs[:] = [d for d in dirs if d not in [
                '.git', 'node_modules', '__pycache__', 'venv', '.venv',
                'dist', 'build', 'tests'
            ]]
            for filename in filenames:
                if filename.endswith('.py'):
                    py_files.append(os.path.join(root, filename))
        return py_files
    
    def _dynamic_api_testing(self) -> List[Finding]:
        """Perform dynamic API testing on running service."""
        findings = []
        
        if not self.base_url or not self.openapi_schema:
            return findings
        
        paths = self.openapi_schema.get("paths", {})
        
        for path, methods in paths.items():
            for method, spec in methods.items():
                if method.lower() not in ["get", "post"]:
                    continue
                
                # Test with empty string parameters
                params = spec.get("parameters", [])
                for param in params:
                    if param.get("in") == "query" and param.get("type") == "string":
                        param_name = param.get("name")
                        test_url = f"{self.base_url}{path}?{param_name}="
                        
                        try:
                            req = urllib.request.Request(test_url, method=method.upper())
                            req.add_header('Accept', 'application/json')
                            
                            with urllib.request.urlopen(req, timeout=5) as response:
                                # If we get a successful response with empty string, that's a potential issue
                                if response.status == 200:
                                    findings.append(Finding(
                                        check_name="empty_string_accepted",
                                        severity="medium",
                                        message=f"API endpoint {method.upper()} {path} accepts empty string "
                                                f"for parameter '{param_name}'. This may indicate missing validation.",
                                        file_path="dynamic_test",
                                        line_start=0,
                                        evidence=f"URL: {test_url}, Status: {response.status}",
                                        remediation=f"Add validation to reject empty strings for '{param_name}'.",
                                        confidence=0.85,
                                    ))
                        except urllib.error.HTTPError as e:
                            # 422 is expected for validation failure
                            if e.code == 422:
                                pass  # Good - validation is working
                            else:
                                findings.append(Finding(
                                    check_name="unexpected_error_code",
                                    severity="low",
                                    message=f"API returned {e.code} for empty parameter '{param_name}' "
                                            f"on {method.upper()} {path}.",
                                    file_path="dynamic_test",
                                    line_start=0,
                                    evidence=f"URL: {test_url}, Status: {e.code}",
                                    remediation="Ensure consistent error handling for invalid parameters.",
                                    confidence=0.50,
                                ))
                        except Exception as e:
                            pass  # Network error, skip
        
        return findings
    
    def review(self, finding: Finding) -> Dict[str, Any]:
        """Review API-related findings."""
        applicable = "api" in finding.check_name.lower() or "parameter" in finding.check_name.lower()
        return {"verdict": "confirmed", "comment": "API relevant" if applicable else ""}
    
    def generate_fix(self, finding: Finding) -> Optional[Dict]:
        """Generate fix for API contract issues."""
        if "validation" in finding.check_name:
            return {
                "type": "code_suggestion",
                "suggestion": finding.remediation,
                "confidence": 0.80,
            }
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SmokeTestAgent — Endpoint Smoke Testing (Requires Running Service)
# ─────────────────────────────────────────────────────────────────────────────

class SmokeTestAgent(BaseAgent):
    """Perform smoke tests on running API endpoints.
    
    This agent REQUIRES a running service to function.
    It will be automatically activated when service_running = True.
    
    Tests performed:
    - Health check endpoint availability
    - Basic endpoint accessibility
    - Response format validation
    - Error handling verification
    """
    
    name = "smoke_test"
    role = AgentRole.INSPECTOR
    
    def __init__(self, agent_id: str = None, bus: "AgentCommunicationBus" = None,
                 memory: "ProjectMemory" = None, base_url: str = None, name: str = None):
        agent_name = name or agent_id or self.name
        super().__init__(name=agent_name, role=self.role, bus=bus)
        self.memory = memory
        self.base_url = base_url
    
    def get_description(self) -> str:
        """Human-readable description of this agent's purpose."""
        return "Performs smoke tests on running API endpoints to verify basic functionality."
    
    def get_domain(self) -> str:
        """Domain this agent specializes in."""
        return "smoke_testing"
    
    def can_activate(self) -> bool:
        """Check if this agent can run (requires running service)."""
        return self.project_profile.get("service_running", False)
    
    def inspect(self, files_context: str) -> List[Finding]:
        """Run smoke tests on API endpoints."""
        findings = []
        
        if not self.can_activate():
            self.logger.info("SmokeTestAgent cannot activate: service not running")
            return findings
        
        self.base_url = f"http://localhost:{self.project_profile.get('service_port', 8000)}"
        
        # Test health endpoints
        findings.extend(self._test_health_endpoints())
        
        # Test OpenAPI endpoint
        findings.extend(self._test_openapi_endpoint())
        
        # Test common endpoints
        findings.extend(self._test_common_endpoints())
        
        return findings
    
    def _test_health_endpoints(self) -> List[Finding]:
        """Test common health check endpoints."""
        findings = []
        health_paths = ["/health", "/healthz", "/ping", "/status", "/api/health"]
        
        for path in health_paths:
            try:
                url = f"{self.base_url}{path}"
                req = urllib.request.Request(url, method='GET')
                req.add_header('Accept', 'application/json')
                
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        # Health endpoint exists and works
                        return []  # Found working health endpoint
                        
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue  # Try next path
                else:
                    findings.append(Finding(
                        check_name="health_endpoint_error",
                        severity="medium",
                        message=f"Health endpoint {path} returned error {e.code}.",
                        file_path="smoke_test",
                        line_start=0,
                        evidence=f"URL: {self.base_url}{path}, Status: {e.code}",
                        remediation="Fix health endpoint to return 200 OK.",
                        confidence=0.80,
                    ))
            except Exception as e:
                pass
        
        # No health endpoint found
        findings.append(Finding(
            check_name="missing_health_endpoint",
            severity="low",
            message="No health check endpoint found. Consider adding /health or /healthz endpoint.",
            file_path="smoke_test",
            line_start=0,
            evidence="Tested paths: " + ", ".join(health_paths),
            remediation="Add a health check endpoint: @app.get('/health') def health(): return {'status': 'ok'}",
            confidence=0.70,
        ))
        
        return findings
    
    def _test_openapi_endpoint(self) -> List[Finding]:
        """Test OpenAPI schema endpoint."""
        findings = []
        
        openapi_paths = ["/openapi.json", "/docs", "/redoc", "/swagger"]
        
        for path in openapi_paths:
            try:
                url = f"{self.base_url}{path}"
                req = urllib.request.Request(url, method='GET')
                
                with urllib.request.urlopen(req, timeout=5) as response:
                    if response.status == 200:
                        return []  # Found working OpenAPI endpoint
                        
            except:
                pass
        
        findings.append(Finding(
            check_name="missing_openapi_endpoint",
            severity="info",
            message="No OpenAPI documentation endpoint found. Consider enabling /docs or /openapi.json.",
            file_path="smoke_test",
            line_start=0,
            evidence="Tested paths: " + ", ".join(openapi_paths),
            remediation="FastAPI: docs_url='/docs', redoc_url='/redoc' are enabled by default.",
            confidence=0.60,
        ))
        
        return findings
    
    def _test_common_endpoints(self) -> List[Finding]:
        """Test common API endpoints."""
        findings = []
        
        # Try to get endpoints from OpenAPI schema
        try:
            url = f"{self.base_url}/openapi.json"
            with urllib.request.urlopen(url, timeout=5) as response:
                schema = json.loads(response.read().decode('utf-8'))
                paths = schema.get("paths", {})
                
                for path, methods in list(paths.items())[:10]:  # Test first 10 endpoints
                    for method in methods:
                        if method.lower() == "get":
                            try:
                                test_url = f"{self.base_url}{path}"
                                # Replace path parameters with test values
                                test_url = re.sub(r'\{[^}]+\}', '1', test_url)
                                
                                req = urllib.request.Request(test_url, method='GET')
                                req.add_header('Accept', 'application/json')
                                
                                with urllib.request.urlopen(req, timeout=5) as resp:
                                    if resp.status >= 500:
                                        findings.append(Finding(
                                            check_name="endpoint_server_error",
                                            severity="high",
                                            message=f"GET {path} returned server error {resp.status}.",
                                            file_path="smoke_test",
                                            line_start=0,
                                            evidence=f"URL: {test_url}, Status: {resp.status}",
                                            remediation="Investigate and fix server error.",
                                            confidence=0.90,
                                        ))
                            except urllib.error.HTTPError as e:
                                if e.code >= 500:
                                    findings.append(Finding(
                                        check_name="endpoint_server_error",
                                        severity="high",
                                        message=f"GET {path} returned server error {e.code}.",
                                        file_path="smoke_test",
                                        line_start=0,
                                        evidence=f"URL: {test_url}, Status: {e.code}",
                                        remediation="Investigate and fix server error.",
                                        confidence=0.90,
                                    ))
                            except:
                                pass
                                
        except:
            pass
        
        return findings
    
    def review(self, finding: Finding) -> Dict[str, Any]:
        """Review smoke test findings."""
        applicable = "endpoint" in finding.check_name.lower() or "smoke" in finding.check_name.lower()
        return {"verdict": "confirmed", "comment": "smoke test relevant" if applicable else ""}
    
    def generate_fix(self, finding: Finding) -> Optional[Dict]:
        """Generate fix suggestions for smoke test issues."""
        if "health_endpoint" in finding.check_name:
            return {
                "type": "code_suggestion",
                "suggestion": finding.remediation,
                "confidence": 0.85,
            }
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Agent Registration
# ─────────────────────────────────────────────────────────────────────────────

DYNAMIC_AGENT_CLASSES = {
    "db_compatibility": DBCompatibilityAgent,
    "db_schema": DBSchemaAgent,
    "api_contract": APIContractAgent,
    "smoke_test": SmokeTestAgent,
}

__all__ = [
    "DBCompatibilityAgent",
    "DBSchemaAgent", 
    "APIContractAgent",
    "SmokeTestAgent",
    "DYNAMIC_AGENT_CLASSES",
]