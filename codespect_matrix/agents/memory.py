"""Dual memory system — project-level memory + global knowledge base."""

from __future__ import annotations

import os
import json
import hashlib
from datetime import datetime, UTC
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Global knowledge base path (cross-project)
GLOBAL_KB_PATH = os.path.join(os.path.expanduser("~"), ".codespect_matrix_knowledge")


class ProjectMemory:
    """Project-level memory.

    Records per-project:
    - Scan history
    - Known false positives
    - Fix decision history
    - Finding fingerprints → decision mappings
    - Convergence trajectory
    """

    MEMORY_FILE = ".codespect_matrix_agent_memory.json"

    def __init__(self, project_path: str):
        self.project_path = project_path
        self.memory_path = os.path.join(project_path, self.MEMORY_FILE)
        self.data = self._load()

    def _load(self) -> Dict:
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "version": "1.0",
            "project": os.path.basename(self.project_path),
            "scans": [],
            "false_positives": {},
            "fix_decisions": [],
            "convergence_history": [],
            "agent_preferences": {},
        }

    def save(self):
        """Persist to disk."""
        with open(self.memory_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False, default=str)

    def fingerprint(self, check_name: str, message: str) -> str:
        """Generate a stable fingerprint for a finding (not cryptographic)."""
        raw = f"{check_name}:{message[:80]}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def is_false_positive(self, check_name: str, message: str) -> bool:
        """Check if a finding is a known false positive."""
        fp = self.fingerprint(check_name, message)
        return fp in self.data["false_positives"]

    def mark_false_positive(self, check_name: str, message: str, reason: str):
        """Mark a finding as false positive."""
        fp = self.fingerprint(check_name, message)
        self.data["false_positives"][fp] = {
            "check_name": check_name,
            "message": message,
            "reason": reason,
            "marked_at": datetime.now(UTC).isoformat(),
        }
        self.save()

    def record_scan(self, round_number: int, issue_count: int,
                    status: str, agent_count: int):
        """Record one scan round."""
        self.data["scans"].append({
            "round": round_number,
            "issue_count": issue_count,
            "status": status,
            "agent_count": agent_count,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        self.data["convergence_history"].append({
            "round": round_number,
            "issue_count": issue_count,
        })
        self.save()

    def record_fix_decision(self, finding: Dict, decision: str, agent: str):
        """Record a fix decision."""
        self.data["fix_decisions"].append({
            "finding": finding,
            "decision": decision,
            "agent": agent,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        self.save()

    def get_recent_scans(self, limit: int = 3) -> List[Dict]:
        """Get most recent scan records."""
        return self.data["scans"][-limit:]

    def get_convergence_trend(self) -> List[Dict]:
        """Get convergence trend data."""
        return self.data["convergence_history"]


class GlobalKnowledgeBase:
    """Cross-project knowledge base.

    Accumulates:
    - Common issue patterns → fix templates
    - Expert recommendation mappings (project profile → agents)
    - False positive rules (reusable across projects)
    - Project type → top-N common issues
    """

    def __init__(self):
        os.makedirs(GLOBAL_KB_PATH, exist_ok=True)
        self.patterns = self._load("patterns.json")
        self.templates = self._load("fix_templates.json")
        self.expert_map = self._load("expert_recommendations.json")
        self.false_positive_rules = self._load("global_false_positives.json")
        self.stats = self._load("stats.json", {
            "projects_analyzed": 0, "issues_found": 0, "issues_fixed": 0,
        })

    def _load(self, filename: str, default=None) -> Any:
        filepath = os.path.join(GLOBAL_KB_PATH, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return default if default is not None else {}

    def _save(self, filename: str, data: Any):
        filepath = os.path.join(GLOBAL_KB_PATH, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def learn_pattern(self, check_name: str, category: str, pattern: str,
                      fix_template: str, severity: str = "medium"):
        """Learn a new issue pattern."""
        key = f"{category}:{check_name}"
        if key not in self.patterns:
            self.patterns[key] = {
                "check_name": check_name,
                "category": category,
                "occurrences": 0,
                "severity": severity,
                "patterns": [],
                "fix_templates": [],
            }
        self.patterns[key]["occurrences"] += 1
        if pattern not in self.patterns[key]["patterns"]:
            self.patterns[key]["patterns"].append(pattern)
        if fix_template not in self.patterns[key]["fix_templates"]:
            self.patterns[key]["fix_templates"].append(fix_template)
        self._save("patterns.json", self.patterns)

    def get_fix_template(self, check_name: str) -> Optional[str]:
        """Get a fix template for a known check."""
        for key, data in self.patterns.items():
            if data.get("check_name") == check_name and data.get("fix_templates"):
                return data["fix_templates"][0]
        return None

    def get_known_patterns(self, limit: int = 20) -> List[Dict]:
        """Get most frequent patterns."""
        sorted_patterns = sorted(
            self.patterns.values(),
            key=lambda x: x.get("occurrences", 0),
            reverse=True,
        )
        return sorted_patterns[:limit]

    def update_expert_map(self, project_type: str, domain: str,
                          recommended_agents: List[str],
                          effectiveness: Dict[str, int]):
        """Update expert recommendation mapping."""
        key = f"{project_type}:{domain}"
        if key not in self.expert_map:
            self.expert_map[key] = {}
        for agent, score in effectiveness.items():
            if agent not in self.expert_map[key]:
                self.expert_map[key][agent] = {"score": 0, "count": 0}
            self.expert_map[key][agent]["score"] += score
            self.expert_map[key][agent]["count"] += 1
        self._save("expert_recommendations.json", self.expert_map)

    def recommend_agents(self, project_type: str, domain: str) -> List[str]:
        """Recommend agents based on project history."""
        key = f"{project_type}:{domain}"
        if key in self.expert_map:
            agents = sorted(
                self.expert_map[key].items(),
                key=lambda x: x[1]["score"] / max(x[1]["count"], 1),
                reverse=True,
            )
            return [a[0] for a in agents[:5]]
        return []

    def add_false_positive_rule(self, pattern: str, category: str):
        """Add a global false positive rule (not cryptographic)."""
        rule_id = hashlib.md5(pattern.encode()).hexdigest()[:8]
        self.false_positive_rules[rule_id] = {
            "pattern": pattern,
            "category": category,
            "added_at": datetime.now(UTC).isoformat(),
            "hit_count": 0,
        }
        self._save("global_false_positives.json", self.false_positive_rules)

    def check_false_positive(self, message: str) -> bool:
        """Check if a message matches a known global false positive."""
        for rule in self.false_positive_rules.values():
            if rule["pattern"].lower() in message.lower():
                rule["hit_count"] += 1
                self._save("global_false_positives.json", self.false_positive_rules)
                return True
        return False

    def record_project_stats(self, project_type: str, issue_count: int,
                             fixed_count: int):
        """Record aggregate project statistics."""
        self.stats["projects_analyzed"] += 1
        self.stats["issues_found"] += issue_count
        self.stats["issues_fixed"] += fixed_count
        self._save("stats.json", self.stats)

    def get_stats(self) -> Dict:
        return dict(self.stats)
