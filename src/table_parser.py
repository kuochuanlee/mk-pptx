"""
純 Python markdown table 解析器，不依賴任何外部套件。

對應計畫 src/table_parser.py，供 build_pptx.py 使用。
"""

from __future__ import annotations


def _parse_row(line: str) -> list[str]:
    """解析單行表格，去除首尾 | 的邊界空白，保留中間空欄位。

    Args:
        line: 表格中的一行文字

    Returns:
        該行各欄位內容的 list
    """
    stripped = line.strip()

    # 去除首尾的 |
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]

    return [cell.strip() for cell in stripped.split("|")]


def parse_markdown_table(md_table: str) -> tuple[list[str], list[list[str]]]:
    """解析 markdown 格式的表格字串。

    回傳 (headers, rows)，其中 headers 為欄位名稱 list，
    rows 為二維 list，每個元素為該格的文字內容。

    Args:
        md_table: markdown 格式的表格字串，
                  可使用真正的換行或 \\n 字面字串。

    Returns:
        tuple[list[str], list[list[str]]]: (headers, rows)

    Raises:
        ValueError: 表格格式不符合要求時

    範例：
        >>> headers, rows = parse_markdown_table(
        ...     "| 項目 | Q1 | Q2 |\\n|---|---|---|\\n| 營收 | 100 | 115 |"
        ... )
        >>> headers
        ['項目', 'Q1', 'Q2']
        >>> rows
        [['營收', '100', '115']]
    """
    # 過濾空行，取得有效行列表
    lines = [
        line.strip()
        for line in md_table.strip().split("\n")
        if line.strip()
    ]

    # 至少要有 header + separator + 1 row
    if len(lines) < 3:
        raise ValueError("markdown table 至少需要 3 行（header + separator + data）")

    # 驗證 header 行包含 `|`
    if "|" not in lines[0]:
        raise ValueError("markdown table header 行必須包含 `|`")

    # 解析 header（第 0 行）
    headers = _parse_row(lines[0])

    if not headers or all(h == "" for h in headers):
        raise ValueError("markdown table header 不可為空")

    # 跳過 separator（第 1 行），解析資料列（第 2 行以後）
    rows: list[list[str]] = []

    for line in lines[2:]:
        rows.append(_parse_row(line))

    return headers, rows
