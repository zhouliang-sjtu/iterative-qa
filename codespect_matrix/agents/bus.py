"""Agent communication bus — debate-style message passing."""

from __future__ import annotations

import uuid
from datetime import datetime, UTC
from typing import Dict, List, Any, Optional, TYPE_CHECKING

from .base import AgentMessage, MessageType, Finding, DebateResult

if TYPE_CHECKING:
    from .base import BaseAgent


class AgentCommunicationBus:
    """Multi-agent communication bus.

    Responsibilities:
    - Message routing (point-to-point + broadcast)
    - Debate management (round control, final ruling)
    - Audit log (complete message history)
    """

    MAX_DEBATE_ROUNDS = 3

    def __init__(self):
        self.messages: List[AgentMessage] = []
        self.debates: Dict[str, Dict] = {}
        self.completed_debates: List[DebateResult] = []
        self.registered_agents: Dict[str, "BaseAgent"] = {}

    def register_agent(self, agent: "BaseAgent"):
        """Register an agent on the bus."""
        self.registered_agents[agent.name] = agent
        agent.bus = self

    def send(self, sender: str, receiver: str, msg_type: MessageType,
             content: str, data: Dict[str, Any] = None,
             reply_to: str = None) -> AgentMessage:
        """Send a message."""
        msg = AgentMessage(
            id=str(uuid.uuid4())[:8],
            sender=sender,
            receiver=receiver,
            msg_type=msg_type,
            content=content,
            data=data or {},
            reply_to=reply_to,
        )
        self.messages.append(msg)
        return msg

    def broadcast_findings(self, sender: str, findings: List[Finding]) -> List[AgentMessage]:
        """Broadcast findings to all other agents."""
        msgs = []
        for f in findings:
            msg = self.send(
                sender=sender,
                receiver="all",
                msg_type=MessageType.FINDING,
                content=f"Finding: [{f.severity.upper()}] {f.check_name}: {f.message}",
                data={"finding": f.to_dict()},
            )
            msgs.append(msg)
        return msgs

    def open_debate(self, finding: Finding, challenger: str, reason: str) -> str:
        """Open a debate session. Returns debate_id."""
        debate_id = str(uuid.uuid4())[:8]
        self.debates[debate_id] = {
            "id": debate_id,
            "finding": finding,
            "challenger": challenger,
            "reason": reason,
            "rounds": [],
            "status": "open",
            "started_at": datetime.now(UTC),
        }

        msg = self.send(
            sender=challenger,
            receiver="orchestrator",
            msg_type=MessageType.CHALLENGE,
            content=f"Challenge {finding.check_name}: {reason}",
            data={"debate_id": debate_id, "finding": finding.to_dict(), "reason": reason},
        )
        self.debates[debate_id]["rounds"].append({
            "role": "challenger", "msg_id": msg.id, "content": msg.content,
        })
        return debate_id

    def close_debate(self, debate_id: str, arbiter: str, ruling: str,
                     rationale: str) -> Optional[DebateResult]:
        """Close a debate with a final ruling."""
        if debate_id not in self.debates:
            return None

        debate = self.debates[debate_id]
        debate["status"] = "closed"
        debate["arbiter"] = arbiter

        result = DebateResult(
            finding=debate["finding"],
            challenger=debate["challenger"],
            defender="",  # filled by caller
            arbiter=arbiter,
            rounds=debate["rounds"],
            final_ruling=ruling,
            rationale=rationale,
        )
        self.completed_debates.append(result)

        self.send(
            sender=arbiter,
            receiver="all",
            msg_type=MessageType.RULING,
            content=f"Ruling: {ruling} — {rationale}",
            data={"debate_id": debate_id, "ruling": ruling},
        )
        return result

    def get_pending_debates(self) -> List[Dict]:
        """Get currently open debates."""
        return [d for d in self.debates.values() if d["status"] == "open"]

    def get_stats(self) -> Dict[str, Any]:
        """Get bus statistics."""
        return {
            "total_messages": len(self.messages),
            "active_debates": len(self.get_pending_debates()),
            "completed_debates": len(self.completed_debates),
            "agents_online": len(self.registered_agents),
            "latest_activity": self.messages[-1].timestamp.isoformat() if self.messages else None,
        }
