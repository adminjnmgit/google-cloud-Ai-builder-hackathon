"""Closed sets of values that were previously bare strings scattered across the code."""

from enum import StrEnum


class RunStatus(StrEnum):
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'


class Source(StrEnum):
    """Where a pipeline run read its reports from."""

    JAGRAN_BIZ = 'jagran_biz'  # the MySQL source table
    CSV = 'csv'  # a file on the server
    UPLOAD = 'upload'  # a file sent to the admin API
    SEED = 'seed'  # a saved feed loaded with `flask orbit seed`

    @classmethod
    def runnable(cls) -> tuple['Source', ...]:
        """Sources a client may ask the pipeline to run on (uploads arrive as files, seeds via the CLI)."""
        return (cls.JAGRAN_BIZ, cls.CSV)


class TagKind(StrEnum):
    INDUSTRY = 'industry'
    CATEGORY = 'category'
