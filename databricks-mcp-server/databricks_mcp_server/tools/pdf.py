"""PDF 工具 - 為 RAG/非結構化資料使用案例產生合成 PDF 文件。"""

import tempfile
from typing import Any, Dict, Literal

from databricks_tools_core.pdf import DocSize
from databricks_tools_core.pdf import generate_pdf_documents as _generate_pdf_documents
from databricks_tools_core.pdf import generate_single_pdf as _generate_single_pdf
from databricks_tools_core.pdf.models import DocumentSpecification

from ..server import mcp


@mcp.tool(timeout=300.0)
def generate_and_upload_pdfs(
    catalog: str,
    schema: str,
    description: str,
    count: int,
    volume: str = "raw_data",
    folder: str = "pdf_documents",
    doc_size: Literal["SMALL", "MEDIUM", "LARGE"] = "MEDIUM",
    overwrite_folder: bool = False,
) -> Dict[str, Any]:
    """
    產生合成 PDF 文件並上傳到 Unity Catalog volume。

    此工具使用 2 步驟流程產生逼真的 PDF 文件：
    1. 使用 LLM 產生多樣化的文件規格
    2. 平行產生 HTML 內容並轉換為 PDF

    每個 PDF 也會附帶一個 companion JSON 檔案，內含 question/guideline 配對，
    用於 RAG 評估。

    參數:
        catalog: Unity Catalog 名稱
        schema: Schema 名稱
        description: PDF 應包含內容的詳細描述。
            請具體說明要涵蓋的領域、文件類型與內容。
            範例："Technical documentation for a cloud infrastructure platform
            including API guides, troubleshooting manuals, and security policies."
        count: 要產生的 PDF 數量（建議：5-20）
        volume: Volume 名稱（必須已存在）。預設："raw_data"
        folder: Volume 內的資料夾（例如 "technical_docs"）。預設："pdf_documents"
        doc_size: 要產生的文件大小。預設："MEDIUM"
            - "SMALL": 約 1 頁，內容精簡
            - "MEDIUM": 約 4-6 頁，涵蓋完整（預設）
            - "LARGE": 約 10 頁以上，內容詳盡
        overwrite_folder: 若為 True，則先刪除既有資料夾內容（預設：False）

    回傳:
        包含以下內容的字典：
        - success: 若所有 PDF 都成功產生則為 True
        - volume_path: 包含 PDF 的 volume 資料夾路徑
        - pdfs_generated: 成功建立的 PDF 數量
        - pdfs_failed: 失敗的 PDF 數量
        - errors: 錯誤訊息清單（若有）

    範例:
        >>> generate_and_upload_pdfs(
        ...     catalog="my_catalog",
        ...     schema="my_schema",
        ...     description="HR policy documents including employee handbook, "
        ...                 "leave policies, code of conduct, and benefits guide",
        ...     count=10,
        ...     doc_size="SMALL"
        ... )
        {
            "success": True,
            "volume_path": "/Volumes/my_catalog/my_schema/raw_data/pdf_documents",
            "pdfs_generated": 10,
            "pdfs_failed": 0,
            "errors": []
        }

    環境變數:
        - DATABRICKS_MODEL: Model serving endpoint 名稱（若未設定則自動探索）
        - DATABRICKS_MODEL_NANO: 較小的 model，可加快產生速度（若未設定則自動探索）
    """
    # 將字串轉換為 DocSize enum
    size_enum = DocSize(doc_size)

    result = _generate_pdf_documents(
        catalog=catalog,
        schema=schema,
        description=description,
        count=count,
        volume=volume,
        folder=folder,
        doc_size=size_enum,
        overwrite_folder=overwrite_folder,
        max_workers=4,
    )

    return {
        "success": result.success,
        "volume_path": result.volume_path,
        "pdfs_generated": result.pdfs_generated,
        "pdfs_failed": result.pdfs_failed,
        "errors": result.errors,
    }


@mcp.tool(timeout=60.0)
def generate_and_upload_pdf(
    title: str,
    description: str,
    question: str,
    guideline: str,
    catalog: str,
    schema: str,
    volume: str = "raw_data",
    folder: str = "pdf_documents",
    doc_size: Literal["SMALL", "MEDIUM", "LARGE"] = "MEDIUM",
) -> Dict[str, Any]:
    """
    產生單一 PDF 文件並上傳到 Unity Catalog volume。

    當你需要建立單一 PDF，並精準控制其內容、標題，
    以及用於 RAG 評估的 question/guideline 時，可使用此工具。

    參數:
        title: 文件標題（例如 "API Authentication Guide"）
        description: 此文件應包含的內容。請詳細描述
            要涵蓋的內容、章節、主題與領域脈絡。
        question: 可透過閱讀此文件回答的問題。
            用於 RAG 評估。
        guideline: 如何評估問題答案是否正確。
            應描述良好答案應包含哪些內容，但不要直接給出確切答案。
        catalog: Unity Catalog 名稱
        schema: Schema 名稱
        volume: Volume 名稱（必須已存在）。預設："raw_data"
        folder: Volume 內的資料夾。預設："pdf_documents"
        doc_size: 要產生的文件大小。預設："MEDIUM"
            - "SMALL": 約 1 頁，內容精簡
            - "MEDIUM": 約 4-6 頁，涵蓋完整
            - "LARGE": 約 10 頁以上，內容詳盡

    回傳:
        包含以下內容的字典：
        - success: 若 PDF 成功產生則為 True
        - pdf_path: 產生的 PDF 在 volume 中的路徑
        - question_path: companion JSON 檔案（question/guideline）的 volume 路徑
        - error: 若產生失敗則為錯誤訊息

    範例:
        >>> generate_and_upload_pdf(
        ...     title="REST API Authentication Guide",
        ...     description="Complete guide to API authentication for a cloud platform "
        ...                 "including OAuth2 flows, API keys, and JWT tokens.",
        ...     question="What are the supported authentication methods?",
        ...     guideline="Answer should mention OAuth2, API keys, and JWT tokens",
        ...     catalog="my_catalog",
        ...     schema="my_schema",
        ...     doc_size="SMALL"
        ... )
        {
            "success": True,
            "pdf_path": "/Volumes/my_catalog/my_schema/raw_data/pdf_documents/rest_api_authentication_guide.pdf",
            "question_path": "/Volumes/my_catalog/my_schema/raw_data/pdf_documents/rest_api_authentication_guide.json",
            "error": None
        }
    """
    # 從 title 產生 model_id（用於檔名）
    import re

    model_id = re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_").upper()

    # 建立文件規格
    doc_spec = DocumentSpecification(
        title=title,
        category="Document",  # 簡化處理 - category 資訊可放在 description 中
        model=model_id,
        description=description,
        question=question,
        guideline=guideline,
    )

    # 將字串轉換為 DocSize enum
    size_enum = DocSize(doc_size)

    # 使用暫存目錄建立本機檔案
    with tempfile.TemporaryDirectory() as temp_dir:
        result = _generate_single_pdf(
            doc_spec=doc_spec,
            description=description,  # 使用相同的 description 作為內容脈絡
            catalog=catalog,
            schema=schema,
            volume=volume,
            folder=folder,
            temp_dir=temp_dir,
            doc_size=size_enum,
        )

    return {
        "success": result.success,
        "pdf_path": result.pdf_path,
        "question_path": result.question_path,
        "error": result.error,
    }
