"""技能優化的共用工具。

從 evaluator.py 擷取而來——提供路徑解析、Token 計數，以及在整個優化套件中使用的 SKILL_KEY 常數。
"""

from pathlib import Path

import tiktoken

SKILL_KEY = "skill_md"


# ---------------------------------------------------------------------------
# 路徑工具
# ---------------------------------------------------------------------------


def find_repo_root() -> Path:
    """向上搜尋 .test/src/ 以找出 repo 根目錄。"""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".test" / "src").exists():
            return current
        if (current / "src" / "skill_test").exists() and current.name == ".test":
            return current.parent
        current = current.parent
    return Path.cwd()


def find_skill_md(skill_name: str) -> Path | None:
    """找出指定技能名稱對應的 SKILL.md 檔案。"""
    repo_root = find_repo_root()
    candidates = [
        repo_root / ".claude" / "skills" / skill_name / "SKILL.md",
        repo_root / "databricks-skills" / skill_name / "SKILL.md",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Token 工具
# ---------------------------------------------------------------------------


def count_tokens(text: str) -> int:
    """使用 cl100k_base 編碼計算 Token 數。"""
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def token_efficiency_score(candidate_text: str, original_token_count: int) -> float:
    """根據候選內容相較於原始內容的精簡程度進行評分。

    比原始內容更小可獲得最高 1.15 的加分，相同大小為 1.0，
    更大則會線性懲罰，在 2 倍大小時降至 0.0。
    """
    if original_token_count <= 0:
        return 1.0
    enc = tiktoken.get_encoding("cl100k_base")
    candidate_tokens = len(enc.encode(candidate_text))
    ratio = candidate_tokens / original_token_count
    if ratio <= 1.0:
        return 1.0 + 0.15 * (1.0 - ratio)
    else:
        return max(0.0, 2.0 - ratio)
