"""Pipeline stages.

Stages are the seam for future distributed execution: each takes its input
explicitly and returns its output explicitly, holding no cross-invocation state,
so a stage could later run on a separate worker without touching business logic.
Phase 5 ships the collect stage; later phases add normalize/dedup/rank/export.
"""

from app.pipeline.stages import CollectStage, PipelineStage

__all__ = ["CollectStage", "PipelineStage"]
