"""
PDF - 合成 PDF 文件產生

使用 LLM 產生逼真的 PDF 文件，適用於 RAG／非結構化資料使用情境。
"""

from .generator import generate_pdf_documents, generate_single_pdf
from .llm import LLMConfigurationError
from .models import (
    DocSize,
    DocumentSpecification,
    DocumentSpecifications,
    PDFBatchResult,
    PDFGenerationResult,
)

__all__ = [
    # 主要函式
    "generate_pdf_documents",
    "generate_single_pdf",
    # 例外
    "LLMConfigurationError",
    # 列舉
    "DocSize",
    # 模型
    "DocumentSpecification",
    "DocumentSpecifications",
    "PDFGenerationResult",
    "PDFBatchResult",
]
