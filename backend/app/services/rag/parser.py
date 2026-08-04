"""文档结构化解析器。

使用 PyMuPDF (fitz) / pymupdf4llm 将复杂 PDF 转换为结构化的 Markdown：
- 保留多级标题层级（H1/H2/H3）
- 将表格转换为 Markdown 表格
- 支持 .md / .txt 直接读入

相比传统 `PyPDFLoader` 按页提取纯文本，本方案保留了文档的层级语义，
便于后续按标题语义切分，显著提升结构化文档（制度、财报等）的问答准确率。
"""
from pathlib import Path

from langchain_core.documents import Document as LCDocument


def parse_document(file_path: str | Path) -> str:
    """将文档解析为结构化的 Markdown 文本。

    返回 Markdown 字符串，供后续语义切分。
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        return _parse_pdf(path)
    if ext in {".md", ".txt"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"不支持的文件类型: {ext}")


def _parse_pdf(path: Path) -> str:
    """使用 pymupdf4llm 将 PDF 转为 Markdown（保留标题与表格）。"""
    import pymupdf4llm

    md = pymupdf4llm.to_markdown(str(path))
    return md


def parse_document_to_langchain(file_path: str | Path) -> list[LCDocument]:
    """解析为 LangChain 文档列表（每个文档带 page 元数据信息）。

    供切分器使用。这里返回单个 Markdown 文档作为一条数据。
    """
    md = parse_document(file_path)
    return [LCDocument(page_content=md, metadata={"source": Path(file_path).name})]