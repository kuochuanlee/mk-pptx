"""
Pydantic Schema 驗證測試。

測試範圍：
  - 各 layout_type 的合法 JSON 驗證
  - 欄位缺漏、類型錯誤
  - slide_number 重複
  - 條件式欄位不一致
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.slide_schema import (
    LayoutType,
    Presentation,
    Slide,
    SlideContent,
)


# ============================================================
# 測試輔助函式
# ============================================================


def make_slide(
    slide_number: int,
    layout_type: str,
    title: str,
    content: dict,
    speaker_notes: str | None = None,
) -> dict:
    """建立 slide dict，供 Slide.model_validate() 使用。"""
    data = {
        "slide_number": slide_number,
        "layout_type": layout_type,
        "title": title,
        "content": content,
    }

    if speaker_notes is not None:
        data["speaker_notes"] = speaker_notes

    return data


def make_presentation(slides: list[dict]) -> dict:
    """建立 presentation dict，供 Presentation.model_validate() 使用。"""
    return {
        "presentation_title": "測試簡報",
        "author": "測試人員",
        "date": "2025-06-01",
        "slides": slides,
    }


# ============================================================
# SlideContent 欄位驗證測試
# ============================================================


class TestSlideContentValidators:
    """SlideContent 欄位層級驗證測試。"""

    def test_bullets_not_empty_valid(self):
        """bullets 有內容時應通過驗證。"""
        content = SlideContent(bullets=["條列一", "條列二"])

        assert content.bullets == ["條列一", "條列二"]

    def test_bullets_empty_raises(self):
        """bullets 為空 list 時應拋出 ValidationError。"""
        with pytest.raises(ValidationError) as exc_info:
            SlideContent(bullets=[])

        assert "bullets 不可為空 list" in str(exc_info.value)

    def test_bullets_none_valid(self):
        """bullets 為 None 時應通過驗證。"""
        content = SlideContent(bullets=None)

        assert content.bullets is None

    def test_markdown_table_valid(self):
        """有效的 markdown table 應通過驗證。"""
        table = "| 項目 | Q1 | Q2 |\n|---|---|---|\n| 營收 | 100 | 115 |"
        content = SlideContent(markdown_table=table)

        assert content.markdown_table == table

    def test_markdown_table_missing_pipe_raises(self):
        """markdown_table 第一行不含 `|` 時應拋出 ValidationError。"""
        with pytest.raises(ValidationError) as exc_info:
            SlideContent(markdown_table="項目 Q1 Q2\n---|---\n100 115")

        assert "第一行必須包含" in str(exc_info.value)

    def test_mermaid_valid_flowchart(self):
        """flowchart 開頭的 mermaid 應通過驗證。"""
        mermaid = "flowchart LR\n  A[開始] --> B[結束]"
        content = SlideContent(mermaid=mermaid)

        assert content.mermaid == mermaid

    def test_mermaid_valid_sequence(self):
        """sequenceDiagram 開頭的 mermaid 應通過驗證。"""
        mermaid = "sequenceDiagram\n  A->>B: 呼叫"
        content = SlideContent(mermaid=mermaid)

        assert content.mermaid == mermaid

    def test_mermaid_valid_state_diagram(self):
        """stateDiagram-v2 開頭的 mermaid 應通過驗證。"""
        mermaid = "stateDiagram-v2\n  [*] --> 待審"
        content = SlideContent(mermaid=mermaid)

        assert content.mermaid == mermaid

    def test_mermaid_invalid_type_raises(self):
        """不支援的 mermaid 圖表類型應拋出 ValidationError。"""
        with pytest.raises(ValidationError) as exc_info:
            SlideContent(mermaid="gantt\n  title 甘特圖")

        assert "合法圖表類型" in str(exc_info.value)

    def test_mermaid_pie_not_supported(self):
        """pie 圖表類型不在支援範圍內，應拋出 ValidationError。"""
        with pytest.raises(ValidationError) as exc_info:
            SlideContent(mermaid="pie\n  title 圓餅圖")

        assert "合法圖表類型" in str(exc_info.value)


# ============================================================
# Slide 條件式欄位驗證測試（各 layout_type）
# ============================================================


class TestSlideLayoutValidation:
    """Slide layout_type 條件式欄位驗證測試。"""

    # ---- title_slide ----

    def test_title_slide_valid(self):
        """title_slide 僅有 subtitle 應通過驗證。"""
        data = make_slide(
            slide_number=1,
            layout_type="title_slide",
            title="Q2 營運報告",
            content={"subtitle": "2025 年第二季"},
        )
        slide = Slide.model_validate(data)

        assert slide.layout_type == LayoutType.TITLE_SLIDE

    def test_title_slide_with_bullets_raises(self):
        """title_slide 含 bullets 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=1,
            layout_type="title_slide",
            title="封面",
            content={"bullets": ["條列一"]},
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "title_slide" in str(exc_info.value)

    def test_title_slide_with_mermaid_raises(self):
        """title_slide 含 mermaid 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=1,
            layout_type="title_slide",
            title="封面",
            content={"mermaid": "flowchart LR\n  A --> B"},
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "title_slide" in str(exc_info.value)

    # ---- section_divider ----

    def test_section_divider_valid(self):
        """section_divider 不含任何 content 欄位應通過驗證。"""
        data = make_slide(
            slide_number=2,
            layout_type="section_divider",
            title="第一章",
            content={},
        )
        slide = Slide.model_validate(data)

        assert slide.layout_type == LayoutType.SECTION_DIVIDER

    def test_section_divider_with_subtitle_valid(self):
        """section_divider 含 subtitle 應通過驗證（subtitle 為可選）。"""
        data = make_slide(
            slide_number=2,
            layout_type="section_divider",
            title="第一章",
            content={"subtitle": "章節說明"},
        )
        slide = Slide.model_validate(data)

        assert slide.content.subtitle == "章節說明"

    # ---- bullets_only ----

    def test_bullets_only_valid(self):
        """bullets_only 含 bullets 應通過驗證。"""
        data = make_slide(
            slide_number=3,
            layout_type="bullets_only",
            title="重點摘要",
            content={"bullets": ["重點一", "重點二", "重點三"]},
        )
        slide = Slide.model_validate(data)

        assert slide.layout_type == LayoutType.BULLETS_ONLY

    def test_bullets_only_missing_bullets_raises(self):
        """bullets_only 缺少 bullets 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=3,
            layout_type="bullets_only",
            title="重點摘要",
            content={},
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "bullets_only" in str(exc_info.value)

    def test_bullets_only_with_table_raises(self):
        """bullets_only 含 markdown_table 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=3,
            layout_type="bullets_only",
            title="重點摘要",
            content={
                "bullets": ["重點一"],
                "markdown_table": "| A | B |\n|---|---|\n| 1 | 2 |",
            },
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "bullets_only" in str(exc_info.value)

    def test_bullets_only_with_mermaid_raises(self):
        """bullets_only 含 mermaid 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=3,
            layout_type="bullets_only",
            title="重點摘要",
            content={
                "bullets": ["重點一"],
                "mermaid": "flowchart LR\n  A --> B",
            },
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "bullets_only" in str(exc_info.value)

    # ---- table_only ----

    def test_table_only_valid(self):
        """table_only 含 markdown_table 應通過驗證。"""
        data = make_slide(
            slide_number=4,
            layout_type="table_only",
            title="數據比較",
            content={
                "markdown_table": "| 項目 | Q1 | Q2 |\n|---|---|---|\n| 營收 | 100 | 115 |"
            },
        )
        slide = Slide.model_validate(data)

        assert slide.layout_type == LayoutType.TABLE_ONLY

    def test_table_only_missing_table_raises(self):
        """table_only 缺少 markdown_table 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=4,
            layout_type="table_only",
            title="數據比較",
            content={},
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "table_only" in str(exc_info.value)

    def test_table_only_with_mermaid_raises(self):
        """table_only 含 mermaid 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=4,
            layout_type="table_only",
            title="數據比較",
            content={
                "markdown_table": "| A |\n|---|\n| 1 |",
                "mermaid": "flowchart LR\n  A --> B",
            },
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "table_only" in str(exc_info.value)

    # ---- bullets_with_table ----

    def test_bullets_with_table_valid(self):
        """bullets_with_table 同時含 bullets 和 markdown_table 應通過驗證。"""
        data = make_slide(
            slide_number=5,
            layout_type="bullets_with_table",
            title="綜合分析",
            content={
                "bullets": ["整體成長 15%"],
                "markdown_table": "| 項目 | Q1 | Q2 |\n|---|---|---|\n| 營收 | 100 | 115 |",
            },
        )
        slide = Slide.model_validate(data)

        assert slide.layout_type == LayoutType.BULLETS_WITH_TABLE

    def test_bullets_with_table_missing_bullets_raises(self):
        """bullets_with_table 缺少 bullets 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=5,
            layout_type="bullets_with_table",
            title="綜合分析",
            content={
                "markdown_table": "| A |\n|---|\n| 1 |",
            },
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "bullets_with_table" in str(exc_info.value)

    def test_bullets_with_table_missing_table_raises(self):
        """bullets_with_table 缺少 markdown_table 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=5,
            layout_type="bullets_with_table",
            title="綜合分析",
            content={"bullets": ["重點一"]},
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "bullets_with_table" in str(exc_info.value)

    # ---- diagram_only ----

    def test_diagram_only_valid(self):
        """diagram_only 含 mermaid 應通過驗證。"""
        data = make_slide(
            slide_number=6,
            layout_type="diagram_only",
            title="流程圖",
            content={"mermaid": "flowchart LR\n  A[開始] --> B[結束]"},
        )
        slide = Slide.model_validate(data)

        assert slide.layout_type == LayoutType.DIAGRAM_ONLY

    def test_diagram_only_missing_mermaid_raises(self):
        """diagram_only 缺少 mermaid 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=6,
            layout_type="diagram_only",
            title="流程圖",
            content={},
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "diagram_only" in str(exc_info.value)

    def test_diagram_only_with_table_raises(self):
        """diagram_only 含 markdown_table 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=6,
            layout_type="diagram_only",
            title="流程圖",
            content={
                "mermaid": "flowchart LR\n  A --> B",
                "markdown_table": "| A |\n|---|\n| 1 |",
            },
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "diagram_only" in str(exc_info.value)

    # ---- bullets_with_diagram ----

    def test_bullets_with_diagram_valid(self):
        """bullets_with_diagram 同時含 bullets 和 mermaid 應通過驗證。"""
        data = make_slide(
            slide_number=7,
            layout_type="bullets_with_diagram",
            title="流程說明",
            content={
                "bullets": ["步驟說明"],
                "mermaid": "flowchart LR\n  A --> B --> C",
            },
        )
        slide = Slide.model_validate(data)

        assert slide.layout_type == LayoutType.BULLETS_WITH_DIAGRAM

    def test_bullets_with_diagram_missing_mermaid_raises(self):
        """bullets_with_diagram 缺少 mermaid 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=7,
            layout_type="bullets_with_diagram",
            title="流程說明",
            content={"bullets": ["步驟說明"]},
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "bullets_with_diagram" in str(exc_info.value)


# ============================================================
# slide_number 驗證測試
# ============================================================


class TestSlideNumberValidation:
    """slide_number 欄位驗證測試。"""

    def test_slide_number_zero_raises(self):
        """slide_number 為 0 應拋出 ValidationError。"""
        data = make_slide(
            slide_number=0,
            layout_type="bullets_only",
            title="測試",
            content={"bullets": ["測試"]},
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "正整數" in str(exc_info.value)

    def test_slide_number_negative_raises(self):
        """slide_number 為負數應拋出 ValidationError。"""
        data = make_slide(
            slide_number=-1,
            layout_type="bullets_only",
            title="測試",
            content={"bullets": ["測試"]},
        )

        with pytest.raises(ValidationError) as exc_info:
            Slide.model_validate(data)

        assert "正整數" in str(exc_info.value)


# ============================================================
# Presentation 層級驗證測試
# ============================================================


class TestPresentationValidation:
    """Presentation 層級驗證測試。"""

    def test_valid_presentation(self):
        """完整合法的 Presentation 應通過驗證。"""
        slides = [
            make_slide(1, "title_slide", "封面", {"subtitle": "副標題"}),
            make_slide(2, "bullets_only", "重點", {"bullets": ["重點一"]}),
        ]
        data = make_presentation(slides)
        prs = Presentation.model_validate(data)

        assert len(prs.slides) == 2

    def test_empty_slides_raises(self):
        """slides 為空 list 應拋出 ValidationError。"""
        data = make_presentation([])

        with pytest.raises(ValidationError) as exc_info:
            Presentation.model_validate(data)

        assert "slides 不可為空 list" in str(exc_info.value)

    def test_duplicate_slide_numbers_raises(self):
        """slide_number 重複應拋出 ValidationError。"""
        slides = [
            make_slide(1, "title_slide", "封面", {"subtitle": "副標題"}),
            make_slide(1, "bullets_only", "重點", {"bullets": ["重點一"]}),
        ]
        data = make_presentation(slides)

        with pytest.raises(ValidationError) as exc_info:
            Presentation.model_validate(data)

        assert "slide_number 重複" in str(exc_info.value)

    def test_multiple_duplicate_slide_numbers_raises(self):
        """多個 slide_number 重複應在錯誤訊息中列出。"""
        slides = [
            make_slide(1, "title_slide", "封面", {"subtitle": "副標題"}),
            make_slide(2, "bullets_only", "重點一", {"bullets": ["條列一"]}),
            make_slide(1, "section_divider", "章節", {}),
            make_slide(2, "bullets_only", "重點二", {"bullets": ["條列二"]}),
        ]
        data = make_presentation(slides)

        with pytest.raises(ValidationError) as exc_info:
            Presentation.model_validate(data)

        error_msg = str(exc_info.value)
        assert "slide_number 重複" in error_msg

    def test_invalid_layout_type_raises(self):
        """無效的 layout_type 應拋出 ValidationError。"""
        slides = [
            make_slide(1, "invalid_layout", "測試", {}),
        ]
        data = make_presentation(slides)

        with pytest.raises(ValidationError):
            Presentation.model_validate(data)

    def test_speaker_notes_optional(self):
        """speaker_notes 為 None 時應通過驗證。"""
        data = make_slide(
            slide_number=1,
            layout_type="bullets_only",
            title="測試",
            content={"bullets": ["條列一"]},
            speaker_notes=None,
        )
        slide = Slide.model_validate(data)

        assert slide.speaker_notes is None

    def test_speaker_notes_present(self):
        """speaker_notes 有內容時應正確儲存。"""
        notes = "請特別強調成本下降的原因。"
        data = make_slide(
            slide_number=1,
            layout_type="bullets_only",
            title="測試",
            content={"bullets": ["條列一"]},
            speaker_notes=notes,
        )
        slide = Slide.model_validate(data)

        assert slide.speaker_notes == notes
