"""
markdown table 解析器測試。

測試範圍：
  - 正常表格解析
  - 少於 3 行（應 raise ValueError）
  - 空格不一致的表格
  - 中文內容
  - 欄位數量不一致（寬鬆處理）
"""

from __future__ import annotations

import pytest

from src.table_parser import parse_markdown_table


# ============================================================
# 正常表格解析測試
# ============================================================


class TestParseMarkdownTableValid:
    """正常 markdown table 解析測試。"""

    def test_basic_english_table(self):
        """基本英文表格應正確解析。"""
        md = "| Name | Value |\n|---|---|\n| foo | 123 |"
        headers, rows = parse_markdown_table(md)

        assert headers == ["Name", "Value"]
        assert rows == [["foo", "123"]]

    def test_basic_chinese_table(self):
        """中文內容表格應正確解析。"""
        md = "| 項目 | Q1 | Q2 |\n|---|---|---|\n| 營收 | 100 | 115 |"
        headers, rows = parse_markdown_table(md)

        assert headers == ["項目", "Q1", "Q2"]
        assert rows == [["營收", "100", "115"]]

    def test_multiple_rows(self):
        """多行資料應全部解析。"""
        md = (
            "| 項目 | Q1 | Q2 |\n"
            "|---|---|---|\n"
            "| 營收 | 100 | 115 |\n"
            "| 成本 | 80 | 74 |\n"
            "| 利潤 | 20 | 41 |"
        )
        headers, rows = parse_markdown_table(md)

        assert headers == ["項目", "Q1", "Q2"]
        assert len(rows) == 3
        assert rows[0] == ["營收", "100", "115"]
        assert rows[1] == ["成本", "80", "74"]
        assert rows[2] == ["利潤", "20", "41"]

    def test_single_row(self):
        """只有一行資料（header + separator + 1 row）應正確解析。"""
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        headers, rows = parse_markdown_table(md)

        assert headers == ["A", "B"]
        assert rows == [["1", "2"]]

    def test_single_column(self):
        """只有一個欄位的表格應正確解析。"""
        md = "| 項目 |\n|---|\n| 數值 |"
        headers, rows = parse_markdown_table(md)

        assert headers == ["項目"]
        assert rows == [["數值"]]

    def test_returns_tuple(self):
        """回傳型別應為 tuple。"""
        md = "| A |\n|---|\n| 1 |"
        result = parse_markdown_table(md)

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_headers_are_list_of_strings(self):
        """headers 應為 list[str]。"""
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        headers, rows = parse_markdown_table(md)

        assert isinstance(headers, list)
        assert all(isinstance(h, str) for h in headers)

    def test_rows_are_list_of_list_of_strings(self):
        """rows 應為 list[list[str]]。"""
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        headers, rows = parse_markdown_table(md)

        assert isinstance(rows, list)
        assert all(isinstance(row, list) for row in rows)
        assert all(isinstance(cell, str) for row in rows for cell in row)


# ============================================================
# 空格不一致的表格測試
# ============================================================


class TestParseMarkdownTableSpaces:
    """空格不一致情況的測試。"""

    def test_extra_spaces_in_cells(self):
        """欄位前後多餘空格應自動去除。"""
        md = "|  項目  |  數值  |\n|---|---|\n|  A  |  100  |"
        headers, rows = parse_markdown_table(md)

        assert headers == ["項目", "數值"]
        assert rows == [["A", "100"]]

    def test_no_spaces_around_pipes(self):
        """沒有空格的緊湊格式應正確解析。"""
        md = "|項目|數值|\n|---|---|\n|A|100|"
        headers, rows = parse_markdown_table(md)

        assert headers == ["項目", "數值"]
        assert rows == [["A", "100"]]

    def test_mixed_spacing(self):
        """不同欄位空格數不一致應正確解析。"""
        md = "| 項目 |數值|  備註  |\n|---|---|---|\n| A |100| OK |"
        headers, rows = parse_markdown_table(md)

        assert headers == ["項目", "數值", "備註"]
        assert rows == [["A", "100", "OK"]]

    def test_leading_trailing_whitespace_in_table(self):
        """整體字串前後有換行應正確處理。"""
        md = "\n| A | B |\n|---|---|\n| 1 | 2 |\n"
        headers, rows = parse_markdown_table(md)

        assert headers == ["A", "B"]
        assert rows == [["1", "2"]]


# ============================================================
# 錯誤情況測試
# ============================================================


class TestParseMarkdownTableErrors:
    """錯誤情況應拋出 ValueError 測試。"""

    def test_only_one_line_raises(self):
        """只有一行應拋出 ValueError。"""
        with pytest.raises(ValueError) as exc_info:
            parse_markdown_table("| A | B |")

        assert "至少需要 3 行" in str(exc_info.value)

    def test_only_two_lines_raises(self):
        """只有兩行應拋出 ValueError。"""
        with pytest.raises(ValueError) as exc_info:
            parse_markdown_table("| A | B |\n|---|---|")

        assert "至少需要 3 行" in str(exc_info.value)

    def test_empty_string_raises(self):
        """空字串應拋出 ValueError。"""
        with pytest.raises(ValueError):
            parse_markdown_table("")

    def test_only_whitespace_raises(self):
        """全為空白字元應拋出 ValueError。"""
        with pytest.raises(ValueError):
            parse_markdown_table("   \n\n   ")

    def test_header_without_pipe_raises(self):
        """header 行不含 `|` 應拋出 ValueError。"""
        with pytest.raises(ValueError) as exc_info:
            parse_markdown_table("A B C\n---|---\n1 2 3")

        assert "header" in str(exc_info.value).lower() or "至少需要 3 行" in str(exc_info.value)


# ============================================================
# 欄位數量不一致的表格測試（寬鬆處理）
# ============================================================


class TestParseMarkdownTableMismatchedColumns:
    """欄位數量不一致的表格測試（table_parser 採寬鬆解析策略）。"""

    def test_row_with_fewer_columns(self):
        """資料列欄位少於 header 時，應仍能解析（不拋出錯誤）。

        寬鬆策略：table_parser 只負責解析，欄位對齊由上層邏輯處理。
        """
        md = "| A | B | C |\n|---|---|---|\n| 1 | 2 |"
        # 不應拋出例外，回傳解析結果
        headers, rows = parse_markdown_table(md)

        assert headers == ["A", "B", "C"]
        # 資料列的欄位數可能少於 header
        assert len(rows) == 1

    def test_row_with_more_columns(self):
        """資料列欄位多於 header 時，應仍能解析（不拋出錯誤）。"""
        md = "| A | B |\n|---|---|\n| 1 | 2 | 3 |"
        headers, rows = parse_markdown_table(md)

        assert headers == ["A", "B"]
        assert len(rows) == 1

    def test_mixed_column_counts(self):
        """不同資料列有不同欄位數時，應全部解析。"""
        md = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n| 4 | 5 |"
        headers, rows = parse_markdown_table(md)

        assert headers == ["A", "B", "C"]
        assert len(rows) == 2


# ============================================================
# 中文與特殊字元測試
# ============================================================


class TestParseMarkdownTableSpecialContent:
    """中文與特殊字元內容測試。"""

    def test_chinese_content_full(self):
        """完整中文內容的表格應正確解析。"""
        md = (
            "| 部門 | 人數 | 達標率 |\n"
            "|---|---|---|\n"
            "| 業務部 | 50 | 95% |\n"
            "| 工程部 | 30 | 88% |"
        )
        headers, rows = parse_markdown_table(md)

        assert headers == ["部門", "人數", "達標率"]
        assert rows[0] == ["業務部", "50", "95%"]
        assert rows[1] == ["工程部", "30", "88%"]

    def test_cells_with_numbers_and_symbols(self):
        """含數字和特殊符號的欄位應正確解析。"""
        md = "| 指標 | 數值 | 狀態 |\n|---|---|---|\n| ROI | 23.5% | 達標 |"
        headers, rows = parse_markdown_table(md)

        assert rows[0] == ["ROI", "23.5%", "達標"]

    def test_separator_with_colons(self):
        """分隔行含對齊冒號（:---:）的表格應正確解析。"""
        md = "| 項目 | 值 |\n|:---|---:|\n| A | 100 |"
        headers, rows = parse_markdown_table(md)

        assert headers == ["項目", "值"]
        assert rows == [["A", "100"]]
