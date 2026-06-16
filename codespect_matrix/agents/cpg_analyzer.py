"""Code Property Graph — AST + Call Graph + Data Flow + Taint Analysis.

Pure Python implementation using built-in `ast` module. No external dependencies.

Capabilities:
1. AST Analysis — find all functions, classes, imports
2. Call Graph — inter-function call dependencies
3. Data Flow Graph — variable definition/use chains
4. Taint Analysis — track untrusted input → dangerous sink paths

Paper value: Elevates codespect-matrix from "regex pattern matching" to
"semantic program analysis", enabling:
- Precise SQL injection detection (taint source → execute)
- PHI flow tracking (patient data → log/output)
- Path traversal (user input → open())
- Cross-function vulnerability chains
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional, Any
from pathlib import Path
from collections import defaultdict, Counter


# ═══════════════════════════════════════════════════════════════════════════════
# Node types
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CodeNode:
    """A node in the property graph — could be a function, class, module, or variable."""
    node_type: str         # "function", "class", "variable", "import", "call"
    name: str
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    parent: str = ""       # parent function/class name
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CodeEdge:
    """An edge in the property graph."""
    edge_type: str         # "calls", "defines", "uses", "imports", "flows_to"
    source: str            # node name
    target: str            # node name
    file_path: str = ""
    line: int = 0
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaintPath:
    """A taint propagation path from source to sink."""
    source_type: str       # "user_input", "phi_data", "untrusted_api"
    source_var: str
    sink_type: str         # "sql_execute", "os_system", "open_file", "log_output", "http_response"
    sink_call: str
    path: List[str]        # variable names along the path
    file_path: str
    line_start: int
    line_end: int
    severity: str
    confidence: float


# ═══════════════════════════════════════════════════════════════════════════════
# Taint sources and sinks — medical software focused
# ═══════════════════════════════════════════════════════════════════════════════

TAINT_SOURCES = {
    # User input
    "request.args.get":       "user_input",
    "request.form.get":       "user_input",
    "request.json":           "user_input",
    "input(":                 "user_input",
    "sys.stdin.read":         "user_input",
    "sys.argv":               "user_input",
    # File input
    "open(":                  "file_input",
    "Path.read_text":         "file_input",
    "json.load":              "file_input",
    "pickle.load":            "untrusted_deserialization",
    "yaml.load":              "untrusted_deserialization",
    # Network input
    "requests.get":           "network_input",
    "socket.recv":            "network_input",
    # PHI data access (medical specific)
    "patient.name":           "phi_data",
    "patient.ssn":            "phi_data",
    "patient_id":             "phi_data",
    "dcm.PatientName":        "phi_dicom_data",
    "dcm.PatientID":          "phi_dicom_data",
}

# Parameter name → taint source type heuristics
PHI_PARAM_PATTERNS = [
    (r'patient|phi|ssn|mrn|dob|name|address|phone|email|diagnosis|medication', 'phi_data'),
    (r'cmd|command|shell|exec|executable', 'user_input'),
    (r'path|file|filename|dir', 'file_input'),
    (r'data|blob|bytes|payload|body|content|json|xml', 'user_input'),
    (r'url|host|endpoint|domain', 'network_input'),
]

NON_TAINT_PARAMS = {'self', 'cls', 'connection', 'conn', 'cursor', 'db', 'database',
                     'session', 'request', 'response', 'config', 'settings', 'logger'}

TAINT_SINKS = {
    "connection.execute":     "sql_execute",
    ".execute(":              "sql_execute",
    # Command execution
    "os.system":              "command_execution",
    "subprocess.run":         "command_execution",
    "subprocess.Popen":       "command_execution",
    "os.popen":               "command_execution",
    "eval(":                  "code_execution",
    "exec(":                  "code_execution",
    # File operations
    "open(":                  "file_operation",
    # Logging (PHI concern)
    "logger.info":            "log_output",
    "logger.debug":           "log_output",
    "logger.warning":         "log_output",
    "print(":                 "log_output",
    "logging.info":           "log_output",
    # HTTP output
    "return":                 "http_response",
    "jsonify":                "http_response",
    "json.dumps":             "serialization",
    # Deserialization
    "pickle.loads":           "deserialization",
    "yaml.load":              "deserialization",
    # Template rendering
    "render_template":        "template_render",
    "render_template_string": "template_render",
}

# Severity mapping for source → sink combinations
TAINT_SEVERITY = {
    ("user_input", "sql_execute"):         ("critical", 0.98),
    ("user_input", "command_execution"):   ("critical", 0.98),
    ("user_input", "code_execution"):      ("critical", 0.99),
    ("user_input", "template_render"):     ("critical", 0.95),
    ("user_input", "file_operation"):      ("high",    0.90),
    ("user_input", "deserialization"):     ("medium",  0.75),
    ("phi_data", "sql_execute"):           ("critical", 0.96),
    ("phi_data", "log_output"):            ("critical", 0.98),
    ("phi_data", "http_response"):         ("critical", 0.97),
    ("phi_data", "serialization"):         ("critical", 0.95),
    ("phi_data", "command_execution"):     ("critical", 0.97),
    ("phi_data", "deserialization"):       ("critical", 0.95),
    ("phi_dicom_data", "log_output"):      ("critical", 0.98),
    ("phi_dicom_data", "http_response"):   ("critical", 0.97),
    ("phi_dicom_data", "serialization"):   ("critical", 0.95),
    ("untrusted_deserialization", "deserialization"): ("critical", 0.96),
    ("file_input", "sql_execute"):         ("high",    0.85),
    ("file_input", "file_operation"):      ("high",    0.88),
    ("network_input", "command_execution"): ("critical", 0.95),
}


def _sink_match(func_name: str, sink_pattern: str) -> bool:
    """Precise sink matching.

    Rules:
    - Exact match: func_name == pattern or clean versions match
    - Dot-prefixed patterns (.execute, .loads) match the suffix of func_name
    - Other patterns match as substring with word-boundary awareness
    """
    clean_pattern = sink_pattern.rstrip('(')
    clean_name = func_name.rstrip('(')

    # Exact match
    if clean_name == clean_pattern:
        return True

    # Dot-prefixed: e.g. ".execute" matches "cursor.execute", "db.execute"
    if clean_pattern.startswith('.'):
        return clean_name.endswith(clean_pattern)

    # Known conflict: "exec" should NOT match "execute"
    # Use word boundary for common over-matching patterns
    conflict_patterns = {'exec', 'eval', 'open'}
    if clean_pattern in conflict_patterns:
        # Must be an exact match on the last component after dot
        last_component = clean_name.rsplit('.', 1)[-1]
        return last_component == clean_pattern

    # Substring match with word-boundary (prevent "open" matching "popen")
    # Split both into dot-separated components, check if any component matches
    pattern_parts = clean_pattern.split('.')
    name_parts = clean_name.split('.')

    # Check for pattern's last component in name's last component (prefix/suffix)
    if len(pattern_parts) >= 1 and len(name_parts) >= 1:
        pp = pattern_parts[-1]
        np = name_parts[-1]
        if pp == np:
            return True
        # Substring match with word boundary check
        if pp in np and len(pp) >= 4:
            # For longer patterns, require word boundary via regex
            if re.search(r'\b' + re.escape(pp) + r'\b', np):
                return True
            return False
        if np in pp and len(np) >= 4:
            return False  # Don't match short names in longer patterns

    return clean_pattern in clean_name


# ═══════════════════════════════════════════════════════════════════════════════
# AST Visitor — builds the graph
# ═══════════════════════════════════════════════════════════════════════════════

class GraphBuilder(ast.NodeVisitor):
    """Walk AST and build nodes + edges."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.nodes: List[CodeNode] = []
        self.edges: List[CodeEdge] = []
        self.current_function: str = ""      # stack-like (simplified)
        self.function_scopes: Dict[str, str] = {}  # function_name → parent_class
        self.current_class: str = ""
        self.variable_defs: Dict[str, Tuple[int, str]] = {}  # var → (line, func)
        self.call_graph: Dict[str, Set[str]] = defaultdict(set)  # caller → callees
        self.imports: Dict[str, str] = {}  # alias → module

    def _add_node(self, node_type: str, name: str, line: int, **props):
        n = CodeNode(
            node_type=node_type, name=name,
            file_path=self.file_path,
            line_start=line, line_end=line,
            parent=self.current_function or self.current_class or "",
            properties=props,
        )
        self.nodes.append(n)
        return n

    def _add_edge(self, edge_type: str, source: str, target: str, line: int):
        e = CodeEdge(
            edge_type=edge_type, source=source, target=target,
            file_path=self.file_path, line=line,
        )
        self.edges.append(e)
        return e

    # ── Top level ──────────────────────────────────────────────────────────

    def visit_FunctionDef(self, node: ast.FunctionDef):
        parent = self.current_function
        self.current_function = node.name
        if self.current_class:
            self.function_scopes[node.name] = self.current_class

        self._add_node("function", node.name, node.lineno,
                       args=[a.arg for a in node.args.args],
                       decorators=[d.id if isinstance(d, ast.Name) else str(d) for d in node.decorator_list])
        # Set end line for scope tracking
        if self.nodes:
            self.nodes[-1].line_end = getattr(node, 'end_lineno', node.lineno)

        self.generic_visit(node)
        self.current_function = parent

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node)  # treat same

    def visit_ClassDef(self, node: ast.ClassDef):
        parent_class = self.current_class
        self.current_class = node.name

        self._add_node("class", node.name, node.lineno,
                       bases=[b.id if isinstance(b, ast.Name) else str(b) for b in node.bases])

        self.generic_visit(node)
        self.current_class = parent_class

    # ── Imports ────────────────────────────────────────────────────────────

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.asname or alias.name
            self.imports[name] = alias.name
            self._add_node("import", name, node.lineno, module=alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            name = alias.asname or alias.name
            self.imports[name] = f"{module}.{alias.name}"
            self._add_node("import", name, node.lineno, module=module, original=alias.name)

    # ── Calls ──────────────────────────────────────────────────────────────

    def visit_Call(self, node: ast.Call):
        func_name = self._resolve_call_name(node.func)
        if func_name:
            self._add_node("call", func_name, node.lineno)

            # Call graph edge: current_function → called_function
            if self.current_function:
                self.call_graph[self.current_function].add(func_name)
                self._add_edge("calls", self.current_function, func_name, node.lineno)

            # Check if this is a taint sink
            for sink_pattern in TAINT_SINKS:
                if _sink_match(func_name, sink_pattern):
                    self._add_edge("potential_sink", func_name, sink_pattern, node.lineno)
                    break

        self.generic_visit(node)

    # ── Assignments (variable definitions) ─────────────────────────────────

    def visit_Assign(self, node: ast.Assign):
        for target in node.targets:
            var_name = self._resolve_name(target)
            if var_name:
                self._add_node("variable", var_name, node.lineno)
                self.variable_defs[var_name] = (node.lineno, self.current_function)

                if self.current_function:
                    self._add_edge("defines", self.current_function, var_name, node.lineno)

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if node.target:
            var_name = self._resolve_name(node.target)
            if var_name:
                self._add_node("variable", var_name, node.lineno)
                self.variable_defs[var_name] = (node.lineno, self.current_function)

    # ── Name references (variable usage) ───────────────────────────────────

    def visit_Name(self, node: ast.Name):
        if isinstance(node.ctx, ast.Load):
            var = node.id
            if var in self.variable_defs:
                def_line, def_func = self.variable_defs[var]
                # Edge: usage → definition
                if def_func and self.current_function:
                    self._add_edge("uses", self.current_function, var, node.lineno)

        self.generic_visit(node)

    # ── Helpers ────────────────────────────────────────────────────────────

    def _resolve_call_name(self, func_node) -> Optional[str]:
        """Resolve call expression to a string name."""
        if isinstance(func_node, ast.Name):
            return func_node.id
        elif isinstance(func_node, ast.Attribute):
            obj = self._resolve_call_name(func_node.value)
            if obj:
                return f"{obj}.{func_node.attr}"
            return func_node.attr
        elif isinstance(func_node, ast.Subscript):
            return self._resolve_call_name(func_node.value)
        return None

    def _resolve_name(self, node) -> Optional[str]:
        """Resolve a name node."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            obj = self._resolve_name(node.value)
            if obj:
                return f"{obj}.{node.attr}"
            return node.attr
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Taint analyzer
# ═══════════════════════════════════════════════════════════════════════════════

class TaintAnalyzer:
    """Track taint propagation through the property graph.

    Algorithm:
    1. Identify taint sources (user input, PHI data access)
    2. Trace variable assignments and data flow
    3. Check if any tainted variable reaches a dangerous sink
    4. Report taint paths with severity
    """

    def __init__(self):
        self.taint_paths: List[TaintPath] = []

    def analyze(self, source_code: str, file_path: str) -> List[TaintPath]:
        """Analyze source code for taint propagation."""
        self.taint_paths = []

        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []

        # Phase 1: Build graph
        builder = GraphBuilder(file_path)
        builder.visit(tree)

        # Phase 2: Identify taint sources and sinks
        sources = self._find_sources(source_code, builder)
        sinks = self._find_sinks(builder)

        # Phase 3: Check for source → sink pairs
        self._check_taint_flows(source_code, sources, sinks, builder)

        return self.taint_paths

    def _find_sources(self, source: str, builder: GraphBuilder) -> Dict[str, List[Tuple[int, str]]]:
        """Find all taint sources in the code."""
        sources: Dict[str, List[Tuple[int, str]]] = defaultdict(list)

        # 1. Detect known taint source patterns in source code
        for line_no, line in enumerate(source.split('\n'), 1):
            for pattern, source_type in TAINT_SOURCES.items():
                if pattern in line:
                    var_match = self._extract_variable(line, pattern)
                    if var_match:
                        sources[source_type].append((line_no, var_match))

        # 2. Function parameters are potential taint sources (with heuristics)
        for node in builder.nodes:
            if node.node_type == "function":
                for arg in node.properties.get("args", []):
                    if arg in NON_TAINT_PARAMS:
                        continue
                    source_type = self._classify_param(arg)
                    sources[source_type].append((node.line_start, arg))

        return sources

    def _find_sinks(self, builder: GraphBuilder) -> Dict[str, List[Tuple[int, str]]]:
        """Find all taint sinks from call nodes."""
        sinks: Dict[str, List[Tuple[int, str]]] = defaultdict(list)

        for node in builder.nodes:
            if node.node_type == "call":
                for pattern, sink_type in TAINT_SINKS.items():
                    if _sink_match(node.name, pattern):
                        sinks[sink_type].append((node.line_start, node.name))

        return sinks

    def _check_taint_flows(
        self,
        source_code: str,
        sources: Dict[str, List[Tuple[int, str]]],
        sinks: Dict[str, List[Tuple[int, str]]],
        builder: GraphBuilder,
    ):
        """Check if any taint source reaches a sink."""
        lines = source_code.split('\n')

        for src_type, src_list in sources.items():
            for src_line, src_var in src_list:
                for sink_type, sink_list in sinks.items():
                    for sink_line, sink_call in sink_list:
                        # Must be in same function or data flows between them
                        if not self._in_same_scope(src_line, sink_line, builder):
                            continue

                        # Check if the tainted variable flows to the sink
                        if self._variable_flows_to(src_var, sink_call, sink_line, lines, builder):
                            sev, conf = TAINT_SEVERITY.get(
                                (src_type, sink_type), ("medium", 0.7)
                            )

                            self.taint_paths.append(TaintPath(
                                source_type=src_type,
                                source_var=src_var,
                                sink_type=sink_type,
                                sink_call=sink_call,
                                path=[src_var, sink_call],
                                file_path=builder.file_path,
                                line_start=src_line,
                                line_end=sink_line,
                                severity=sev,
                                confidence=conf,
                            ))
                            break  # one match per source

    def _in_same_scope(self, line1: int, line2: int, builder: GraphBuilder) -> bool:
        """Check if two lines are in the same function scope (approximate)."""

        func_at_line1 = self._get_function_at_line(line1, builder)
        func_at_line2 = self._get_function_at_line(line2, builder)

        if func_at_line1 is None and func_at_line2 is None:
            return True  # both in module scope
        return func_at_line1 == func_at_line2

    def _get_function_at_line(self, line: int, builder: GraphBuilder) -> Optional[str]:
        """Get the function that contains a given line."""
        func_nodes = [n for n in builder.nodes if n.node_type == "function"]
        func_nodes.sort(key=lambda n: n.line_start)

        for fn in func_nodes:
            if fn.line_start <= line <= fn.line_end:
                return fn.name
        return None

    def _variable_flows_to(
        self, var: str, sink: str, sink_line: int,
        lines: List[str], builder: GraphBuilder,
    ) -> bool:
        """Check if variable flows to a sink call — supports transitive taint.

        Handles:
        - Direct: var appears in sink call
        - Transitive: var → intermediate → sink
        - F-string: var in f-string assigned to intermediate, intermediate reaches sink
        """
        if sink_line > len(lines):
            return False

        sink_code = lines[sink_line - 1]

        # Direct: variable appears as argument in the sink call
        if var in sink_code:
            return True

        # Transitive: find assignments that reference var, then check if those reach sink
        tainted_vars = {var}
        for line_no in range(1, sink_line + 1):
            if line_no > len(lines):
                break
            line = lines[line_no - 1]

            for tv in list(tainted_vars):
                if tv in line and '=' in line:
                    # This line assigns from a tainted variable
                    m = re.match(r'\s*(\w+)\s*[=:]\s*', line)
                    if m:
                        new_var = m.group(1)
                        if new_var != tv and new_var != var:
                            tainted_vars.add(new_var)

        # Check if any tainted variable reaches the sink
        for tv in tainted_vars:
            if tv in sink_code:
                return True

        return False

    @staticmethod
    def _classify_param(param_name: str) -> str:
        """Classify a function parameter name into taint source type."""
        for pattern, stype in PHI_PARAM_PATTERNS:
            if re.search(pattern, param_name, re.IGNORECASE):
                return stype
        return "user_input"  # default

    @staticmethod
    def _extract_variable(line: str, pattern: str) -> Optional[str]:
        """Extract the variable name being assigned from a line."""
        # Pattern like: var = request.args.get(...)
        m = re.search(r'(\w+)\s*[=:]\s*.*' + re.escape(pattern), line)
        if m:
            return m.group(1)

        # Pattern like: request.args.get(...) directly in call
        m = re.search(r'(\w+)\s*=\s*.*' + re.escape(pattern), line)
        if m:
            return m.group(1)

        # Default: the pattern itself
        return pattern.split('.')[0] if '.' in pattern else pattern


# ═══════════════════════════════════════════════════════════════════════════════
# CPG Report Generator
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class CPGReport:
    """Complete analysis report from Code Property Graph."""
    file_path: str
    total_functions: int
    total_classes: int
    total_imports: int
    total_calls: int
    call_graph_edges: int
    taint_paths: List[TaintPath]
    critical_paths: int
    high_paths: int


class CPGAnalyzer:
    """Main entry point for CPG analysis of a project."""

    def analyze_file(self, file_path: str, source_code: str) -> CPGReport:
        """Analyze a single file."""
        taint = TaintAnalyzer()
        taint_paths = taint.analyze(source_code, file_path)

        # Build graph for stats
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return CPGReport(
                file_path=file_path, total_functions=0, total_classes=0,
                total_imports=0, total_calls=0, call_graph_edges=0,
                taint_paths=[], critical_paths=0, high_paths=0,
            )

        builder = GraphBuilder(file_path)
        builder.visit(tree)

        funcs = sum(1 for n in builder.nodes if n.node_type == "function")
        classes = sum(1 for n in builder.nodes if n.node_type == "class")
        imports = sum(1 for n in builder.nodes if n.node_type == "import")
        calls = sum(1 for n in builder.nodes if n.node_type == "call")
        call_edges = sum(len(v) for v in builder.call_graph.values())

        critical = sum(1 for p in taint_paths if p.severity == "critical")
        high = sum(1 for p in taint_paths if p.severity == "high")

        return CPGReport(
            file_path=file_path, total_functions=funcs, total_classes=classes,
            total_imports=imports, total_calls=calls, call_graph_edges=call_edges,
            taint_paths=taint_paths, critical_paths=critical, high_paths=high,
        )

    def analyze_project(self, files: Dict[str, str]) -> List[CPGReport]:
        """Analyze multiple files. files = {path: source_code}."""
        reports = []
        for path, code in files.items():
            if path.endswith('.py'):
                report = self.analyze_file(path, code)
                reports.append(report)
        return reports

    def summary(self, reports: List[CPGReport]) -> Dict[str, Any]:
        """Generate summary across all analyzed files."""
        total_taint = sum(len(r.taint_paths) for r in reports)
        total_critical = sum(r.critical_paths for r in reports)
        total_high = sum(r.high_paths for r in reports)

        # Group by taint type
        by_type: Dict[str, int] = defaultdict(int)
        for r in reports:
            for p in r.taint_paths:
                key = f"{p.source_type} → {p.sink_type}"
                by_type[key] += 1

        return {
            "files_analyzed": len(reports),
            "total_functions": sum(r.total_functions for r in reports),
            "total_classes": sum(r.total_classes for r in reports),
            "taint_paths_total": total_taint,
            "critical_paths": total_critical,
            "high_paths": total_high,
            "by_taint_type": dict(Counter(by_type).most_common(10)),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Integration helper — convert CPG findings to RuleFinding format
# ═══════════════════════════════════════════════════════════════════════════════

def taint_to_rule_findings(taint_path: TaintPath) -> Dict[str, Any]:
    """Convert a TaintPath to a healthcare_rules-compatible finding dict."""
    messages = {
        ("user_input", "sql_execute"): "Taint analysis: user input flows to SQL execution — potential SQL injection",
        ("user_input", "command_execution"): "Taint analysis: user input flows to command execution — potential RCE",
        ("user_input", "code_execution"): "Taint analysis: user input flows to code execution — critical RCE risk",
        ("phi_data", "log_output"): "Taint analysis: PHI data flows to log output — HIPAA violation",
        ("phi_data", "http_response"): "Taint analysis: PHI data flows to HTTP response — data leak",
        ("phi_dicom_data", "log_output"): "Taint analysis: DICOM PHI data flows to log output — HIPAA violation",
        ("untrusted_deserialization", "deserialization"): "Taint analysis: untrusted data flows to deserialization — RCE risk",
    }

    key = (taint_path.source_type, taint_path.sink_type)
    msg = messages.get(key, f"Taint analysis: {taint_path.source_type} → {taint_path.sink_type}")

    return {
        "check_name": f"cpg_taint_{taint_path.source_type}_to_{taint_path.sink_type}",
        "severity": taint_path.severity,
        "message": msg,
        "file_path": taint_path.file_path,
        "line_start": taint_path.line_start,
        "line_end": taint_path.line_end,
        "evidence": f"Variable '{taint_path.source_var}' flows to '{taint_path.sink_call}'",
        "remediation": _remediation_for_path(taint_path),
        "confidence": taint_path.confidence,
    }


def _remediation_for_path(path: TaintPath) -> str:
    """Generate remediation advice for a taint path."""
    remediations = {
        "sql_execute": "Use parameterized queries. Never concatenate user input into SQL.",
        "command_execution": "Avoid shell=True. Use subprocess.run with list args. Validate all inputs.",
        "code_execution": "Never use eval/exec on user input. Use ast.literal_eval for safe parsing.",
        "log_output": "Redact PHI from logs. Use structured logging with PHI scrubbing.",
        "http_response": "Sanitize and validate all response data. Never include raw PHI in responses.",
        "deserialization": "Use safe deserializers. Never unpickle untrusted data. Use json instead.",
        "template_render": "Use auto-escaping template engines. Never pass user input to render_template_string.",
        "file_operation": "Validate and sanitize file paths. Use pathlib and whitelist allowed directories.",
    }
    return remediations.get(path.sink_type, "Validate and sanitize all data flows. Implement proper input validation.")


# ═══════════════════════════════════════════════════════════════════════════════
# Quick scan API
# ═══════════════════════════════════════════════════════════════════════════════

def scan_project_cpg(project_path: str, files: List[Tuple[str, str]]) -> List[Dict]:
    """Run CPG analysis on a project. Returns list of finding dicts."""
    analyzer = CPGAnalyzer()
    file_map = {path: code for path, code in files if path.endswith('.py')}
    reports = analyzer.analyze_project(file_map)

    findings = []
    for report in reports:
        for path in report.taint_paths:
            finding = taint_to_rule_findings(path)
            findings.append(finding)

    return findings
