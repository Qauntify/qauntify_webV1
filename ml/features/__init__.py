"""Offline access to the canonical production-safe feature builder."""

from signals.ml.features import CandidateFeatureInput, build_candidate_features

__all__ = ["CandidateFeatureInput", "build_candidate_features"]
