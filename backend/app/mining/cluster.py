"""Failure mining: discover *novel* failure clusters from production traces
without a predefined list of known bugs.

Pipeline: trace summaries -> TF-IDF embeddings -> HDBSCAN clustering.
HDBSCAN is chosen over k-means deliberately: it doesn't require specifying
the number of clusters up front (we don't know how many distinct failure
modes exist in a given window), it natively labels low-density points as
noise (-1) instead of forcing every trace into a cluster, and cluster
density/size gives a real signal for "is this worth turning into a
regression task" (a cluster of 2 might be a fluke; a cluster of 40 is a
real recurring problem).

In production the embedding step would call an embedding model via
LangChain; here TF-IDF over trace summaries is used so clustering is
fully deterministic and testable offline, while the clustering algorithm
itself (the actual interesting part) is the real thing.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer


@dataclass
class TraceSummary:
    trace_id: str
    summary: str  # short natural-language description of what went wrong
    agent_version: str


@dataclass
class FailureCluster:
    cluster_id: str
    trace_ids: list[str]
    representative_summary: str
    size: int
    discovered_at: datetime = field(default_factory=datetime.utcnow)


def embed_summaries(summaries: list[str]) -> np.ndarray:
    """TF-IDF embedding — deterministic, no external API, good enough to
    separate genuinely different failure descriptions by vocabulary overlap.
    Swappable for a real embedding model's output without changing the
    clustering code below, since clustering only depends on the matrix shape."""
    if not summaries:
        return np.empty((0, 0))
    vectorizer = TfidfVectorizer(stop_words="english", max_features=512)
    matrix = vectorizer.fit_transform(summaries)
    return matrix.toarray()


def cluster_failures(
    traces: list[TraceSummary],
    min_cluster_size: int = 3,
) -> list[FailureCluster]:
    """Returns one FailureCluster per discovered group of >= min_cluster_size
    traces with similar failure descriptions. Traces HDBSCAN labels as noise
    (label -1) are dropped — a singleton or pair of similar-looking failures
    isn't yet a pattern worth promoting into a regression task."""
    if len(traces) < min_cluster_size:
        return []

    summaries = [t.summary for t in traces]
    embeddings = embed_summaries(summaries)
    if embeddings.shape[1] == 0:
        return []

    clusterer = HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean")
    labels = clusterer.fit_predict(embeddings)

    grouped: dict[int, list[int]] = defaultdict(list)
    for idx, label in enumerate(labels):
        if label == -1:
            continue  # noise point, not a cluster
        grouped[label].append(idx)

    clusters: list[FailureCluster] = []
    for label, indices in grouped.items():
        member_traces = [traces[i] for i in indices]
        # representative = the summary closest to the cluster centroid
        cluster_embeddings = embeddings[indices]
        centroid = cluster_embeddings.mean(axis=0)
        distances = np.linalg.norm(cluster_embeddings - centroid, axis=1)
        representative_idx = indices[int(np.argmin(distances))]

        clusters.append(
            FailureCluster(
                cluster_id=f"cluster-{uuid.uuid4().hex[:8]}",
                trace_ids=[t.trace_id for t in member_traces],
                representative_summary=traces[representative_idx].summary,
                size=len(member_traces),
            )
        )

    clusters.sort(key=lambda c: c.size, reverse=True)
    return clusters
