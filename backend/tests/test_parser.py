"""文档解析器测试。"""
from pathlib import Path

import fitz

from app.services.rag.parser import parse_document


def _make_pdf(path: Path) -> None:
    """生成一个含标题与正文的简体中文 PDF。"""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "员工手册", fontsize=20, fontname="china-s")
    page.insert_text((72, 110), "1. 考勤制度", fontsize=14, fontname="china-s")
    page.insert_text(
        (72, 130), "公司实行每周五天工作制，工作时间上午9点到下午6点。",
        fontsize=10, fontname="china-s",
    )
    doc.save(str(path))
    doc.close()


def test_parse_pdf_keeps_heading_structure(tmp_path):
    pdf = tmp_path / "sample.pdf"
    _make_pdf(pdf)
    md = parse_document(pdf)
    assert "员工手册" in md
    assert "考勤制度" in md
    # 标题被转换为 Markdown 标题
    assert "#" in md


def test_parse_markdown_direct(tmp_path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("# 标题\n正文内容", encoding="utf-8")
    assert parse_document(md_file) == "# 标题\n正文内容"


def test_parse_unsupported_extension(tmp_path):
    bad = tmp_path / "doc.docx"
    bad.write_bytes(b"x")
    try:
        parse_document(bad)
        assert False, "应当抛出 ValueError"
    except ValueError:
        pass