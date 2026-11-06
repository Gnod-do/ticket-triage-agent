"""Core data records shared by all pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

TICKET_TYPES = ("bug", "feature_request", "service_request", "consultation", "other")
USER_IMPACTS = ("blocker", "degraded", "cosmetic")
PRODUCTS = ("webneft", "fuel_cards")


@dataclass
class Ticket:
    ticket_id: str
    product_id: str
    customer_id: str
    channel: str  # "portal" | "call"
    source_created_at: datetime
    ingested_at: datetime
    text: str
    gt_cluster: str | None = None  # ground truth, used only by evaluation
    gt_type: str = "other"


@dataclass
class Enrichment:
    ticket_id: str
    type: str
    feature: str
    problem_summary: str
    user_impact: str
    confidence: float


@dataclass
class ClusterStats:
    cluster_id: str
    product_id: str
    ticket_ids: list[str]
    n_tickets: int
    n_customers: int
    weekly_counts: dict[str, int]
    first_seen: datetime
    last_seen: datetime
    trend: str  # "rising" | "stable" | "falling"


@dataclass
class DigestItem:
    cluster_id: str
    product_id: str
    title: str
    summary: str
    scale_text: str
    evidence_ids: list[str]
    hypothesis: str
    action: str
    owner_team: str
    channel: str


@dataclass
class Alert:
    cluster_id: str
    product_id: str
    hour: datetime
    count: int
    baseline: float
    sample_ids: list[str] = field(default_factory=list)
