"""用於 PDF 產生的 Pydantic 模型。"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class DocSize(str, Enum):
    """PDF 產生的文件大小選項。"""

    SMALL = "SMALL"  # 約 1 頁
    MEDIUM = "MEDIUM"  # 約 5 頁（預設）
    LARGE = "LARGE"  # 約 10 頁以上


class DocumentSpecification(BaseModel):
    """單一待產生文件的規格。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(description="文件具描述性且專業的標題")
    category: str = Field(description="文件類別（例如：Technical、Procedures、Guides、Templates、Reference）")
    model: str = Field(description="文件的唯一識別碼／代碼")
    description: str = Field(
        description="文件內容的詳細摘要，需參照特定任務與脈絡"
    )
    question: str = Field(description="可透過閱讀此文件回答的具體問題")
    guideline: str = Field(
        description="用於評估答案的準則──定義語氣、結構與行為的期待"
    )


class DocumentSpecifications(BaseModel):
    """文件規格集合。"""

    model_config = ConfigDict(extra="forbid")

    documents: list[DocumentSpecification]


class PDFGenerationResult(BaseModel):
    """產生單一 PDF 的結果。"""

    pdf_path: str
    question_path: Optional[str] = None
    success: bool
    error: Optional[str] = None


class PDFBatchResult(BaseModel):
    """批次產生 PDF 的結果。"""

    success: bool
    volume_path: str
    pdfs_generated: int
    pdfs_failed: int
    errors: list[str] = Field(default_factory=list)
