"""
Lakebase Autoscaling 操作

用於管理 Databricks Lakebase Autoscaling 專案、分支、
compute（端點）與資料庫認證的函式。
"""

from .projects import (
    create_project,
    get_project,
    list_projects,
    update_project,
    delete_project,
)
from .branches import (
    create_branch,
    get_branch,
    list_branches,
    update_branch,
    delete_branch,
)
from .computes import (
    create_endpoint,
    get_endpoint,
    list_endpoints,
    update_endpoint,
    delete_endpoint,
)
from .credentials import (
    generate_credential,
)

__all__ = [
    # 專案
    "create_project",
    "get_project",
    "list_projects",
    "update_project",
    "delete_project",
    # 分支
    "create_branch",
    "get_branch",
    "list_branches",
    "update_branch",
    "delete_branch",
    # Compute（端點）
    "create_endpoint",
    "get_endpoint",
    "list_endpoints",
    "update_endpoint",
    "delete_endpoint",
    # 認證
    "generate_credential",
]
