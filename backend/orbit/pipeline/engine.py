"""Pure pipeline: reports in, {meta, events} out. No database, no I/O.

Batch agents, in order: Translate (observe) → Weight / Extract (JEV-alike classify) → Episode.
"""

from ..agents.pipeline import EXCLUDED_SECTIONS, run_pipeline

__all__ = ['EXCLUDED_SECTIONS', 'run_pipeline']
