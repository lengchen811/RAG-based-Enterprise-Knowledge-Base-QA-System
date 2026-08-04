"""语义切分（父子文档）测试。"""
from app.services.rag.splitter import (
    build_child_store,
    build_parent_lookup,
    split_markdown,
)

SAMPLE = """# 员工手册

## 考勤制度
公司实行每周五天工作制，工作时间上午9点到下午6点。
员工上下班需使用钉钉打卡，迟到超过30分钟算迟到。

## 休假制度
### 年假
员工入职满一年后，每年享有5天带薪年假。
### 事假
事假需提前一天申请，经直属主管批准。

# 报销制度
报销需提供发票原件，金额超过500元需部门负责人审批。
"""


def test_split_creates_semantic_parents():
    parents = split_markdown(SAMPLE, document_id=1, filename="手册.md")
    # 至少拆出 考勤 / 休假 / 报销 等语义块
    texts = [p.parent_text for p in parents]
    joined = "\n".join(texts)
    assert "考勤制度" in joined
    assert "休假制度" in joined
    assert "报销制度" in joined


def test_each_parent_has_children():
    parents = split_markdown(SAMPLE, document_id=1, filename="手册.md")
    assert len(parents) >= 1
    for p in parents:
        assert p.children, "每个 Parent 至少应有一个 Child"
        assert p.parent_id
        assert all(c.parent_id == p.parent_id for c in p.children)


def test_child_store_and_parent_lookup():
    parents = split_markdown(SAMPLE, document_id=1, filename="手册.md")
    children = build_child_store(parents)
    lookup = build_parent_lookup(parents)
    assert len(children) == sum(len(p.children) for p in parents)
    assert len(lookup) == len(parents)
    # 每个 child 都能通过 parent_id 找到 parent 文本
    for c in children:
        assert c.parent_id in lookup


def test_metadata_carries_document_info():
    parents = split_markdown(SAMPLE, document_id=1, filename="手册.md")
    c = parents[0].children[0]
    assert c.metadata["document_id"] == 1
    assert c.metadata["filename"] == "手册.md"