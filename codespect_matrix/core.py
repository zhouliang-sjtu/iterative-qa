"""Core service — project analysis via ProjectScanner (agent mode).

Since v1.0 the legacy rule engine and QAService have been removed.
For full review, use `AgentOrchestrator` directly.
For evolution analysis, use `codespect_matrix.evolution`.
"""

import os
from typing import Dict, Optional

from .models import ProjectProfile
from .scanner import ProjectScanner


def analyze_project(project_path: str = ".") -> ProjectProfile:
    """Analyze project characteristics via ProjectScanner.
    
    This is the lightweight entry point used by AgentOrchestrator.initialize().
    """
    scanner = ProjectScanner()
    return scanner.scan(project_path)
