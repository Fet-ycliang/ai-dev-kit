"""DatasetSource abstraction - YAML-only initially, UC interface defined for later."""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Protocol
import yaml


@dataclass
class EvalRecord:
    """Standard evaluation record format (matches databricks-mlflow-evaluation patterns)."""

    id: str
    inputs: Dict[str, Any]
    outputs: Optional[Dict[str, Any]] = None  # Pre-computed for Pattern 2
    expectations: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_eval_dict(self) -> Dict[str, Any]:
        """Convert to MLflow evaluation format."""
        result = {"inputs": self.inputs}
        if self.outputs:
            result["outputs"] = self.outputs
        if self.expectations:
            result["expectations"] = self.expectations
        return result


class DatasetSource(Protocol):
    """Protocol for dataset sources - enables future UC integration."""

    def load(self) -> List[EvalRecord]:
        """Load evaluation records."""
        ...


@dataclass
class YAMLDatasetSource:
    """Load evaluation dataset from YAML file (Phase 1 implementation)."""

    yaml_path: Path

    def load(self) -> List[EvalRecord]:
        """Load records from YAML ground_truth.yaml file.

        Supports external response files via 'expected_response_file' field in outputs.
        When present, the response is loaded from the file relative to the YAML directory.
        """
        with open(self.yaml_path) as f:
            data = yaml.safe_load(f)

        yaml_dir = self.yaml_path.parent

        records = []
        for case in data.get("test_cases", []):
            outputs = case.get("outputs")

            # 若已指定外部檔案，從中載入回應
            if outputs and "expected_response_file" in outputs:
                response_file = yaml_dir / outputs["expected_response_file"]
                if response_file.exists():
                    with open(response_file) as rf:
                        outputs = dict(outputs)  # 複製以避免修改原始資料
                        outputs["response"] = rf.read()
                        del outputs["expected_response_file"]

            records.append(
                EvalRecord(
                    id=case["id"],
                    inputs=case["inputs"],
                    outputs=outputs,
                    expectations=case.get("expectations"),
                    metadata=case.get("metadata", {}),
                )
            )
        return records

    def save(self, records: List[EvalRecord]) -> None:
        """將記錄儲存回 YAML 檔案。"""
        data = {
            "test_cases": [
                {
                    "id": r.id,
                    "inputs": r.inputs,
                    "outputs": r.outputs,
                    "expectations": r.expectations,
                    "metadata": r.metadata,
                }
                for r in records
            ]
        }
        with open(self.yaml_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


@dataclass
class UCDatasetSource:
    """從 Unity Catalog 載入評估資料集（Phase 2 - 僅為 stub）。"""

    uc_table_name: str

    def load(self) -> List[EvalRecord]:
        """UC 整合的佔位符。"""
        raise NotImplementedError("UC datasets deferred to Phase 2. Use YAMLDatasetSource for now.")


def get_dataset_source(skill_name: str, base_path: Path = None) -> DatasetSource:
    """取得技能的適當資料集來源。"""
    if base_path is None:
        # Try relative to this module first (works from any cwd)
        module_base = Path(__file__).parent.parent / "skills"
        if module_base.exists():
            base_path = module_base
        else:
            # Fallback: try common paths
            for candidate in [Path("skills"), Path(".test/skills")]:
                if candidate.exists():
                    base_path = candidate
                    break
            else:
                base_path = Path(".test/skills")

    yaml_path = base_path / skill_name / "ground_truth.yaml"
    if yaml_path.exists():
        return YAMLDatasetSource(yaml_path)

    raise FileNotFoundError(f"No ground_truth.yaml found for {skill_name}")
