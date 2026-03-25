"""
SQL Utilities - SQL 作業的內部輔助工具。
"""

from .executor import SQLExecutor, SQLExecutionError
from .dependency_analyzer import SQLDependencyAnalyzer
from .parallel_executor import SQLParallelExecutor
from .models import (
    TableStatLevel,
    HistogramBin,
    ColumnDetail,
    DataSourceInfo,
    TableInfo,  # DataSourceInfo 的別名
    TableSchemaResult,
    VolumeFileInfo,
    VolumeFolderResult,  # DataSourceInfo 的別名
)
from .table_stats_collector import TableStatsCollector

__all__ = [
    "SQLExecutor",
    "SQLExecutionError",
    "SQLDependencyAnalyzer",
    "SQLParallelExecutor",
    "TableStatLevel",
    "HistogramBin",
    "ColumnDetail",
    "DataSourceInfo",
    "TableInfo",  # DataSourceInfo 的別名
    "TableSchemaResult",
    "VolumeFileInfo",
    "VolumeFolderResult",  # DataSourceInfo 的別名
    "TableStatsCollector",
]
