"""Aggregation methods for multi-LLM ensembles (survey §7.2).

Seven aggregators are provided, all sharing the same `aggregate` API:
    VerifierOutput -> AggregatedDecision

Inputs are lightweight dataclasses so callers can construct test
fixtures without subclassing.
"""

from .base import (
    VerifierOutput,
    AggregatedDecision,
    Aggregator,
)
from .implementations import (
    MajorityVote,
    PBFTThreshold,
    UniformWeightedMean,
    EMAWeightedMean,
    EMAWeightedMedian,
    KalmanFilterTrust,
    AdaptiveHybrid,
    AGGREGATOR_REGISTRY,
    make_aggregator,
)

__all__ = [
    "VerifierOutput",
    "AggregatedDecision",
    "Aggregator",
    "MajorityVote",
    "PBFTThreshold",
    "UniformWeightedMean",
    "EMAWeightedMean",
    "EMAWeightedMedian",
    "KalmanFilterTrust",
    "AdaptiveHybrid",
    "AGGREGATOR_REGISTRY",
    "make_aggregator",
]