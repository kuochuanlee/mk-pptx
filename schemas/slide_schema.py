"""
Pydantic 資料模型定義。

對應計畫 schemas/slide_schema.py，定義簡報 JSON 的 Schema 與驗證規則。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, field_validator, model_validator


class LayoutType(str, Enum):
    """投影片版面類型列舉。"""

    TITLE_SLIDE = "title_slide"
    SECTION_DIVIDER = "section_divider"
    BULLETS_ONLY = "bullets_only"
    TABLE_ONLY = "table_only"
    BULLETS_WITH_TABLE = "bullets_with_table"
    DIAGRAM_ONLY = "diagram_only"
    BULLETS_WITH_DIAGRAM = "bullets_with_diagram"


# 支援的 mermaid 圖表類型關鍵字
VALID_MERMAID_TYPES = (
    "flowchart",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram-v2",
    "erDiagram",
)


class SlideContent(BaseModel):
    """投影片內容欄位，依 layout_type 使用不同欄位組合。"""

    # 條列文字（bullets_only、bullets_with_table、bullets_with_diagram 使用）
    bullets: Optional[list[str]] = None

    # Markdown 格式的表格字串（table_only、bullets_with_table 使用）
    markdown_table: Optional[str] = None

    # Mermaid 語法字串（diagram_only、bullets_with_diagram 使用）
    mermaid: Optional[str] = None

    # 封面頁與章節分隔頁的副標題（title_slide、section_divider 使用）
    subtitle: Optional[str] = None

    @field_validator("bullets")
    @classmethod
    def bullets_not_empty(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """bullets 若存在，不可為空 list。"""
        if v is not None and len(v) == 0:
            raise ValueError("bullets 不可為空 list")

        return v

    @field_validator("markdown_table")
    @classmethod
    def markdown_table_format(cls, v: Optional[str]) -> Optional[str]:
        """markdown_table 若存在，第一行必須包含 `|`。"""
        if v is None:
            return v

        first_line = v.strip().split("\n")[0]
        if "|" not in first_line:
            raise ValueError("markdown_table 第一行必須包含 `|`")

        return v

    @field_validator("mermaid")
    @classmethod
    def mermaid_valid_type(cls, v: Optional[str]) -> Optional[str]:
        """mermaid 若存在，開頭必須是合法的圖表類型關鍵字。"""
        if v is None:
            return v

        stripped = v.strip()
        is_valid = any(stripped.startswith(t) for t in VALID_MERMAID_TYPES)

        if not is_valid:
            valid_list = "、".join(VALID_MERMAID_TYPES)
            raise ValueError(
                f"mermaid 開頭必須是合法圖表類型之一：{valid_list}"
            )

        return v


class Slide(BaseModel):
    """單頁投影片資料模型。"""

    # 投影片序號，必須為正整數
    slide_number: int

    # 版面類型
    layout_type: LayoutType

    # 投影片標題
    title: str

    # 演講者備註（可選）
    speaker_notes: Optional[str] = None

    # 投影片內容
    content: SlideContent

    @field_validator("slide_number")
    @classmethod
    def slide_number_positive(cls, v: int) -> int:
        """slide_number 必須為正整數。"""
        if v <= 0:
            raise ValueError("slide_number 必須為正整數")

        return v

    @model_validator(mode="after")
    def validate_content_by_layout(self) -> "Slide":
        """依 layout_type 執行條件式欄位驗證。"""
        layout = self.layout_type
        content = self.content

        # 各 layout 對應的欄位需求定義
        if layout == LayoutType.TABLE_ONLY:
            # table_only：必須有 markdown_table，不可有 mermaid
            self._require_fields(layout, content, required=["markdown_table"])
            self._forbid_fields(layout, content, forbidden=["mermaid", "bullets"])

        elif layout == LayoutType.DIAGRAM_ONLY:
            # diagram_only：必須有 mermaid，不可有 markdown_table
            self._require_fields(layout, content, required=["mermaid"])
            self._forbid_fields(layout, content, forbidden=["markdown_table", "bullets"])

        elif layout == LayoutType.BULLETS_WITH_TABLE:
            # bullets_with_table：必須同時有 bullets + markdown_table
            self._require_fields(layout, content, required=["bullets", "markdown_table"])
            self._forbid_fields(layout, content, forbidden=["mermaid"])

        elif layout == LayoutType.BULLETS_WITH_DIAGRAM:
            # bullets_with_diagram：必須同時有 bullets + mermaid
            self._require_fields(layout, content, required=["bullets", "mermaid"])
            self._forbid_fields(layout, content, forbidden=["markdown_table"])

        elif layout == LayoutType.BULLETS_ONLY:
            # bullets_only：必須有 bullets，不可有 markdown_table 或 mermaid
            self._require_fields(layout, content, required=["bullets"])
            self._forbid_fields(layout, content, forbidden=["markdown_table", "mermaid"])

        elif layout in (LayoutType.TITLE_SLIDE, LayoutType.SECTION_DIVIDER):
            # title_slide / section_divider：不可有 bullets、markdown_table、mermaid
            self._forbid_fields(
                layout, content, forbidden=["bullets", "markdown_table", "mermaid"]
            )

        return self

    @staticmethod
    def _require_fields(
        layout: LayoutType,
        content: SlideContent,
        required: list[str],
    ) -> None:
        """驗證 content 中必要欄位是否存在。"""
        for field in required:
            if getattr(content, field) is None:
                raise ValueError(
                    f"layout_type '{layout.value}' 的 content 必須包含 '{field}' 欄位"
                )

    @staticmethod
    def _forbid_fields(
        layout: LayoutType,
        content: SlideContent,
        forbidden: list[str],
    ) -> None:
        """驗證 content 中禁止出現的欄位。"""
        for field in forbidden:
            if getattr(content, field) is not None:
                raise ValueError(
                    f"layout_type '{layout.value}' 的 content 不可包含 '{field}' 欄位"
                )


class Presentation(BaseModel):
    """整份簡報的頂層資料模型。"""

    # 簡報標題
    presentation_title: str

    # 作者
    author: str

    # 日期（格式：YYYY-MM-DD）
    date: str

    # 投影片清單，不可為空
    slides: list[Slide]

    @field_validator("slides")
    @classmethod
    def slides_not_empty(cls, v: list[Slide]) -> list[Slide]:
        """slides 不可為空 list。"""
        if len(v) == 0:
            raise ValueError("slides 不可為空 list")

        return v

    @model_validator(mode="after")
    def validate_unique_slide_numbers(self) -> "Presentation":
        """slide_number 在所有 slides 中不可重複。"""
        numbers = [s.slide_number for s in self.slides]
        seen: set[int] = set()
        duplicates: list[int] = []

        for num in numbers:
            if num in seen:
                duplicates.append(num)
            seen.add(num)

        if duplicates:
            raise ValueError(
                f"以下 slide_number 重複出現：{duplicates}"
            )

        return self
