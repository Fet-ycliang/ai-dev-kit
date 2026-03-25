"""使用 optimize_anything API 的 GEPA 技能優化。

公開 API：
    optimize_skill()              - 端對端優化 SKILL.md（以及可選的工具）
    create_skillbench_evaluator() - 為技能建立基於評判器的評估器
    OptimizationResult            - 包含優化結果的 Dataclass
    PRESETS                       - GEPA 配置預設（quick、standard、thorough）
"""

from .runner import optimize_skill, OptimizationResult
from .skillbench_evaluator import create_skillbench_evaluator
from .config import PRESETS
from .review import review_optimization, apply_optimization

__all__ = [
    "optimize_skill",
    "OptimizationResult",
    "create_skillbench_evaluator",
    "PRESETS",
    "review_optimization",
    "apply_optimization",
]
