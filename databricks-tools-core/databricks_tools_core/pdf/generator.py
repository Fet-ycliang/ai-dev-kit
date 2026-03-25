"""使用 LLM 與平行化處理產生 PDF 文件。"""

import json
import logging
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from ..auth import get_workspace_client
from ..unity_catalog.volume_files import upload_to_volume
from .llm import call_llm
from .models import (
    DocSize,
    DocumentSpecification,
    DocumentSpecifications,
    PDFBatchResult,
    PDFGenerationResult,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 驗證
# =============================================================================


def _validate_volume_path(catalog: str, schema: str, volume: str) -> None:
    """驗證 catalog、schema 與 volume 是否存在。

    引發：
        ValueError: 任一元件不存在時引發
    """
    w = get_workspace_client()

    # 檢查 schema 是否存在（也會一併驗證 catalog）
    try:
        w.schemas.get(full_name=f"{catalog}.{schema}")
    except Exception as e:
        raise ValueError(f"Schema '{catalog}.{schema}' 不存在：{e}") from e

    # 檢查 volume 是否存在
    try:
        w.volumes.read(name=f"{catalog}.{schema}.{volume}")
    except Exception as e:
        raise ValueError(f"Volume '{catalog}.{schema}.{volume}' 不存在：{e}") from e


# =============================================================================
# 提示詞
# =============================================================================

# 文件產生的大小設定
_SIZE_CONFIG = {
    DocSize.SMALL: {
        "pages": "1 頁",
        "max_tokens": 4000,
        "content_guidance": "請保持精簡且聚焦，只包含最必要的資訊。",
        "structure": (
            "使用簡單結構：標題、簡短引言、主要內容（2-3 個短章節）與結論。"
        ),
    },
    DocSize.MEDIUM: {
        "pages": "4-6 頁",
        "max_tokens": 12000,
        "content_guidance": "提供完整且細節適度的內容，並納入範例與說明。",
        "structure": (
            "使用標準結構：標題、目錄、引言、"
            "多個詳細章節、範例與結論。"
        ),
    },
    DocSize.LARGE: {
        "pages": "10 頁以上",
        "max_tokens": 20000,
        "content_guidance": (
            "內容需完整且詳盡，包含大量範例、邊界情況、疑難排解與附錄。"
        ),
        "structure": (
            "使用完整結構：封面頁、目錄、執行摘要、"
            "含子章節的多個章節、詳細範例、附錄與詞彙表。"
        ),
    },
}


def _get_document_list_prompt(description: str, count: int) -> str:
    """產生文件清單生成用的 prompt。"""
    return f"""請根據以下描述，產生剛好 {count} 份文件規格：

描述：{description}

每份文件都必須包含：
- title: 專業且具描述性的標題
- category: Technical、Procedures、Guides、Templates、Reference 其中之一
- model: 唯一 ID（例如："DOC-001"、"PROC-AUTH-01"）
- description: 文件包含的內容，需帶出上述描述中的具體細節
- question: 可透過閱讀此文件回答的具體問題
- guideline: 如何評估答案是否正確（不要直接給出精確答案）

請讓文件具多樣性，涵蓋描述中的不同面向。請剛好產生 {count} 份文件。"""


def _get_html_generation_prompt(doc_spec: DocumentSpecification, description: str, doc_size: DocSize) -> str:
    """產生 HTML 內容生成用的 prompt。"""
    config = _SIZE_CONFIG[doc_size]

    return f"""請為 RAG 應用產生專業的 HTML5 文件。

文件：
- 標題：{doc_spec.title}
- 類別：{doc_spec.category}
- ID：{doc_spec.model}
- 描述：{doc_spec.description}

情境：{description}

目標長度：{config["pages"]}

內容指引：{config["content_guidance"]}

結構：{config["structure"]}

請產生完整且有效的 HTML5（<!DOCTYPE html>, <html>, <head>, <style>, <body>）。不要加入 markdown 包裝。"""


def _get_html_system_prompt(doc_size: DocSize) -> str:
    """依據文件大小取得 HTML 生成用的 system prompt。"""
    base_prompt = """你是技術文件專家，負責建立可轉換為 PDF 的 HTML 文件。

文件類型調整：
- Technical: 精準語言、程式碼範例、程序
- HR/Policy: 親切語氣、政策說明、常見問題
- Training: 教學語氣、目標、練習
- User Guides: 清楚語言、情境、提示

HTML 要求：
- 完整 HTML5：<!DOCTYPE html>, <html>, <head>, <style>, <body>
- 僅輸出有效的 HTML，不要加入 markdown 包裝
- 專業格式：標題（h1-h4）、段落、清單、表格

CSS 要求（關鍵 - PyMuPDF 相容性）：
- 只使用 CSS 2.1 語法
- 不可使用 CSS variables (--var-name)
- 不可使用複雜選擇器（:has、:is、:where）
- 只能使用簡單選擇器：.class、element
- 安全屬性：color、background-color、font-family、font-size、margin、padding、border、text-align"""

    size_specific = {
        DocSize.SMALL: """

小型文件（約 1 頁）：
- 內容簡短且聚焦
- 最多 2-3 個短章節
- 不需要目錄
- 僅包含必要資訊
- 最少樣式""",
        DocSize.MEDIUM: """

中型文件（約 4-6 頁）：
- 內容涵蓋完整
- 含錨點連結的目錄
- 多個含範例的章節
- 細節程度均衡
- 專業樣式""",
        DocSize.LARGE: """

大型文件（約 10 頁以上）：
- 內容完整且詳盡
- 詳細目錄
- 多個含子章節的章節
- 大量範例與程式碼片段
- 疑難排解章節
- 附錄與參考資料
- 完整專業樣式""",
    }

    return base_prompt + size_specific[doc_size]


# =============================================================================
# HTML 轉 PDF
# =============================================================================


def _convert_html_to_pdf(html_content: str, output_path: str) -> bool:
    """使用 PyMuPDF 將 HTML 內容轉換為 PDF。

    參數：
        html_content: 要轉換的 HTML 字串
        output_path: PDF 應儲存的位置

    回傳：
        成功時為 True，否則為 False
    """
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import fitz  # PyMuPDF

        logger.debug(f"正在使用 PyMuPDF 將 HTML 轉換為 PDF：{output_path}")

        # 從 HTML 建立 Story
        story = fitz.Story(html=html_content)

        # 建立 DocumentWriter
        writer = fitz.DocumentWriter(output_path)

        # 定義頁面版面配置函式
        def rect_fn(page_num, filled_rect):
            page_rect = fitz.Rect(0, 0, 595, 842)  # A4 頁面大小（單位：點）
            content_rect = fitz.Rect(50, 50, 545, 792)  # 邊界（50pt = 約 0.7 吋）
            footer_rect = fitz.Rect(0, 0, 0, 0)  # 不使用頁尾區域
            return page_rect, content_rect, footer_rect

        # 以適當的分頁與格式將 story 寫入 PDF
        story.write(writer, rect_fn)
        writer.close()

        # 檢查檔案是否成功建立
        if Path(output_path).exists():
            file_size = Path(output_path).stat().st_size
            logger.info(f"PDF 已儲存：{output_path}（大小：{file_size:,} bytes）")
            return True
        else:
            logger.error("PyMuPDF 轉換失敗 - 未建立檔案")
            return False

    except ImportError:
        logger.error("尚未安裝 PyMuPDF。請使用以下指令安裝：pip install pymupdf")
        return False
    except Exception as e:
        logger.error(f"HTML 轉 PDF 失敗：{str(e)}", exc_info=True)
        return False


# =============================================================================
# VOLUME 操作
# =============================================================================


def _delete_folder_contents(catalog: str, schema: str, volume: str, folder: str, max_workers: int = 5) -> None:
    """平行刪除 volume 資料夾中的所有檔案。"""
    w = get_workspace_client()
    volume_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}"

    def delete_file(file_path: str) -> bool:
        try:
            w.files.delete(file_path)
            logger.debug(f"已刪除：{file_path}")
            return True
        except Exception as e:
            logger.warning(f"無法刪除 {file_path}：{e}")
            return False

    try:
        files = list(w.files.list_directory_contents(volume_path))
        if not files:
            return

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(delete_file, f.path): f.path for f in files}
            for future in as_completed(futures):
                future.result()  # 若有例外則拋出

        logger.info(f"已清空資料夾內容：{volume_path}（{len(files)} 個檔案）")
    except Exception as e:
        # 資料夾可能尚不存在，這是可接受的
        logger.debug(f"資料夾不存在或無法列出：{volume_path} - {e}")


def _upload_to_volume(local_path: str, catalog: str, schema: str, volume: str, folder: str, filename: str) -> bool:
    """將檔案上傳到 volume，必要時建立資料夾。"""
    from ..unity_catalog.volume_files import create_volume_directory

    folder_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}"
    volume_path = f"{folder_path}/{filename}"

    # 確保資料夾存在
    try:
        create_volume_directory(folder_path)
    except Exception as e:
        logger.debug(f"資料夾可能已存在：{folder_path} - {e}")

    result = upload_to_volume(local_path, volume_path, overwrite=True)
    if result.success:
        logger.debug(f"已上傳：{volume_path}")
        return True
    else:
        logger.error(f"無法將 {local_path} 上傳至 {volume_path}：{result.error}")
        return False


# =============================================================================
# 單一 PDF 產生
# =============================================================================


def generate_single_pdf(
    doc_spec: DocumentSpecification,
    description: str,
    catalog: str,
    schema: str,
    volume: str,
    folder: str,
    temp_dir: str,
    doc_size: DocSize = DocSize.MEDIUM,
) -> PDFGenerationResult:
    """根據文件規格產生單一 PDF。

    參數：
        doc_spec: 包含標題、描述等資訊的文件規格
        description: 整體情境描述
        catalog: Unity Catalog 名稱
        schema: Schema 名稱
        volume: Volume 名稱
        folder: Volume 內的資料夾
        temp_dir: 用於建立本機檔案的暫存目錄
        doc_size: 要產生的文件大小（SMALL、MEDIUM、LARGE）。預設：MEDIUM

    回傳：
        包含路徑與成功狀態的 PDFGenerationResult

    引發：
        ValueError: 若 catalog、schema 或 volume 不存在
    """
    # 在進行任何 LLM 工作前，先確認 volume 路徑存在
    _validate_volume_path(catalog, schema, volume)

    try:
        # 依據 model 識別碼產生安全的檔名
        safe_name = doc_spec.model.replace(" ", "_").replace("-", "_").lower()

        logger.info(f"正在產生 PDF：{doc_spec.title}（{safe_name}）- 大小：{doc_size.value}")

        # 步驟 1：產生 HTML 內容
        html_prompt = _get_html_generation_prompt(doc_spec, description, doc_size)
        system_prompt = _get_html_system_prompt(doc_size)
        max_tokens = _SIZE_CONFIG[doc_size]["max_tokens"]

        t0 = time.time()
        html_content = call_llm(
            prompt=html_prompt,
            system_prompt=system_prompt,
            mini=True,
            max_tokens=max_tokens,
        )
        logger.info(f"[{safe_name}] LLM call took {time.time() - t0:.1f}s")

        # 步驟 2：將 HTML 轉換為 PDF
        pdf_filename = f"{safe_name}.pdf"
        local_pdf_path = str(Path(temp_dir) / pdf_filename)

        if not _convert_html_to_pdf(html_content, local_pdf_path):
            return PDFGenerationResult(
                pdf_path="",
                success=False,
                error=f"無法將 {doc_spec.title} 的 HTML 轉換為 PDF",
            )

        # 步驟 3：將 PDF 上傳至 volume
        if not _upload_to_volume(local_pdf_path, catalog, schema, volume, folder, pdf_filename):
            return PDFGenerationResult(
                pdf_path="",
                success=False,
                error=f"無法上傳 {doc_spec.title} 的 PDF",
            )

        volume_pdf_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}/{pdf_filename}"

        # 步驟 4：儲存 question/guideline JSON
        question_data = {
            "title": doc_spec.title,
            "category": doc_spec.category,
            "pdf_path": volume_pdf_path,
            "question": doc_spec.question,
            "guideline": doc_spec.guideline,
        }

        json_filename = f"{safe_name}.json"
        local_json_path = str(Path(temp_dir) / json_filename)

        with open(local_json_path, "w") as f:
            json.dump(question_data, f, indent=2)

        volume_json_path = None
        if _upload_to_volume(local_json_path, catalog, schema, volume, folder, json_filename):
            volume_json_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}/{json_filename}"

        logger.info(f"已成功產生：{doc_spec.title}")

        return PDFGenerationResult(
            pdf_path=volume_pdf_path,
            question_path=volume_json_path,
            success=True,
        )

    except Exception as e:
        error_msg = f"產生 {doc_spec.title} 的 PDF 時發生錯誤：{str(e)}"
        logger.error(error_msg, exc_info=True)
        return PDFGenerationResult(
            pdf_path="",
            success=False,
            error=error_msg,
        )


# =============================================================================
# 主要進入點
# =============================================================================


def generate_pdf_documents(
    catalog: str,
    schema: str,
    description: str,
    count: int,
    volume: str = "raw_data",
    folder: str = "pdf_documents",
    doc_size: DocSize = DocSize.MEDIUM,
    overwrite_folder: bool = False,
    max_workers: int = 4,
    temp_dir: Optional[str] = None,
) -> PDFBatchResult:
    """根據描述產生多份 PDF 文件。

    這是 PDF 產生的主要進入點，流程分為 2 個步驟：
    1. 使用 LLM 產生文件規格清單
    2. 根據這些規格平行產生 PDF

    參數：
        catalog: Unity Catalog 名稱
        schema: Schema 名稱
        description: PDF 應包含內容的詳細描述
        count: 要產生的 PDF 數量
        volume: Volume 名稱（必須已存在）。預設："raw_data"
        folder: Volume 中存放 PDF 的資料夾。預設："pdf_documents"
        doc_size: 文件大小（SMALL=約 1 頁、MEDIUM=約 5 頁、LARGE=約 10 頁以上）。預設：MEDIUM
        overwrite_folder: 若為 True，先刪除既有資料夾內容（預設：False）
        max_workers: 同時進行的 PDF 產生上限（預設：4）
        temp_dir: 本機 PDF 檔案的可選目錄（產生後會保留）。
                  若為 None，則使用會自動清理的暫存目錄。

    回傳：
        含成功狀態與統計資訊的 PDFBatchResult

    引發：
        ValueError: 若 catalog、schema 或 volume 不存在
    """
    volume_path = f"/Volumes/{catalog}/{schema}/{volume}/{folder}"
    errors: list[str] = []

    logger.info(f"開始產生 PDF：{count} 份文件，輸出至 {volume_path}")

    # 在進行任何 LLM 工作前，先確認 volume 路徑存在
    _validate_volume_path(catalog, schema, volume)

    try:
        # 若有要求則清空資料夾
        if overwrite_folder:
            logger.info(f"正在清空既有資料夾內容：{volume_path}")
            _delete_folder_contents(catalog, schema, volume, folder)

        # 步驟 1：產生文件規格
        logger.info(f"步驟 1：正在產生 {count} 份文件規格...")

        doc_list_prompt = _get_document_list_prompt(description, count)
        system_prompt = """你是技術文件領域的專家。\
請根據提供的描述產生文件規格。

請回傳一個 JSON 物件，其中包含 "documents" 陣列，且數量必須與要求完全一致。\
每份文件都應包含：
- title: string
- category: string（Technical、Procedures、Guides、Templates、Reference 其中之一）
- model: string（唯一識別碼，例如 DOC-001）
- description: string
- question: string
- guideline: string"""

        t0 = time.time()
        doc_list_response = call_llm(
            prompt=doc_list_prompt,
            system_prompt=system_prompt,
            mini=True,
            max_tokens=8000,
            response_format="json_object",
        )
        logger.info(f"步驟 1 的 LLM 呼叫耗時 {time.time() - t0:.1f}s")

        try:
            response_data = json.loads(doc_list_response)
            doc_specs_model = DocumentSpecifications(**response_data)
            document_specs = doc_specs_model.documents
        except (json.JSONDecodeError, ValueError) as e:
            error_msg = f"無法解析文件規格：{e}。回應內容：{doc_list_response[:500]}"
            logger.error(error_msg)
            return PDFBatchResult(
                success=False,
                volume_path=volume_path,
                pdfs_generated=0,
                pdfs_failed=count,
                errors=[error_msg],
            )

        if not document_specs:
            return PDFBatchResult(
                success=False,
                volume_path=volume_path,
                pdfs_generated=0,
                pdfs_failed=count,
                errors=["回應中未產生任何文件"],
            )

        logger.info(f"已產生 {len(document_specs)} 份文件規格")

        # 步驟 2：平行產生 PDF
        logger.info(f"步驟 2：正在產生 PDF（並行數：{max_workers}）...")

        def run_pdf_generation(working_dir: str) -> list:
            """在指定目錄中執行 PDF 產生工作。"""
            results = []

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        generate_single_pdf,
                        doc_spec=doc_spec,
                        description=description,
                        catalog=catalog,
                        schema=schema,
                        volume=volume,
                        folder=folder,
                        temp_dir=working_dir,
                        doc_size=doc_size,
                    ): doc_spec
                    for doc_spec in document_specs
                }

                for future in as_completed(futures):
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        results.append(e)

            return results

        # 使用提供的 temp_dir，或建立暫存目錄
        if temp_dir:
            Path(temp_dir).mkdir(parents=True, exist_ok=True)
            results = run_pdf_generation(temp_dir)
        else:
            with tempfile.TemporaryDirectory() as auto_temp_dir:
                results = run_pdf_generation(auto_temp_dir)

        # 處理結果
        pdfs_generated = 0
        pdfs_failed = 0

        for result in results:
            if isinstance(result, Exception):
                errors.append(str(result))
                pdfs_failed += 1
            elif isinstance(result, PDFGenerationResult):
                if result.success:
                    pdfs_generated += 1
                else:
                    pdfs_failed += 1
                    if result.error:
                        errors.append(result.error)

        success = pdfs_generated > 0 and pdfs_failed == 0

        logger.info(f"PDF 產生完成：{pdfs_generated}/{len(document_specs)} 成功")

        return PDFBatchResult(
            success=success,
            volume_path=volume_path,
            pdfs_generated=pdfs_generated,
            pdfs_failed=pdfs_failed,
            errors=errors,
        )

    except Exception as e:
        error_msg = f"PDF 產生失敗：{str(e)}"
        logger.error(error_msg, exc_info=True)
        return PDFBatchResult(
            success=False,
            volume_path=volume_path,
            pdfs_generated=0,
            pdfs_failed=count,
            errors=[error_msg],
        )
