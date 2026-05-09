"""
validate.py 的測試模組。

使用 mock LLMClient 進行測試，不需要真實 API 呼叫。
覆蓋：一次成功、JSON 失敗後 retry、Pydantic 失敗後 retry、
超過重試上限、markdown code block 去除、retry prompt 內容驗證。
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from schemas.slide_schema import Presentation
from src.validate import _build_retry_prompt, _strip_markdown_fences, validate_and_retry


# ---------------------------------------------------------------
# 共用測試資料
# ---------------------------------------------------------------

# 合法的 Presentation JSON 字串（最小可通過驗證的範例）
VALID_JSON_STR = json.dumps(
    {
        "presentation_title": "測試簡報",
        "author": "測試者",
        "date": "2026-05-09",
        "slides": [
            {
                "slide_number": 1,
                "layout_type": "title_slide",
                "title": "歡迎",
                "speaker_notes": "這是封面頁。",
                "content": {},
            }
        ],
    },
    ensure_ascii=False,
)

# 不合法的 JSON 字串（缺少右括號）
INVALID_JSON_STR = '{"presentation_title": "測試", "author": "測試者"'

# 合法 JSON 但 Pydantic 驗證會失敗（缺少必要欄位 slides）
INVALID_PYDANTIC_STR = json.dumps(
    {
        "presentation_title": "測試簡報",
        "author": "測試者",
        "date": "2026-05-09",
    },
    ensure_ascii=False,
)


def _make_mock_client(*responses: str) -> MagicMock:
    """建立依序回傳指定字串的 mock LLMClient。

    Args:
        responses: 依序回傳的字串（side_effect 清單）

    Returns:
        mock LLMClient 物件
    """
    mock_client = MagicMock()
    mock_client.generate.side_effect = list(responses)
    return mock_client


# ---------------------------------------------------------------
# _strip_markdown_fences 單元測試
# ---------------------------------------------------------------

class TestStripMarkdownFences:
    """測試 markdown code block 去除輔助函式。"""

    def test_strip_json_fence(self) -> None:
        """去除 ```json ... ``` 格式。"""
        wrapped = "```json\n{\"key\": \"value\"}\n```"
        result = _strip_markdown_fences(wrapped)
        assert result == '{"key": "value"}'

    def test_strip_plain_fence(self) -> None:
        """去除 ``` ... ``` 格式（無語言標記）。"""
        wrapped = "```\n{\"key\": \"value\"}\n```"
        result = _strip_markdown_fences(wrapped)
        assert result == '{"key": "value"}'

    def test_no_fence_unchanged(self) -> None:
        """無 code block 包裝時，原樣回傳。"""
        plain = '{"key": "value"}'
        result = _strip_markdown_fences(plain)
        assert result == plain

    def test_strip_with_extra_whitespace(self) -> None:
        """包裝前後有多餘空白時也能正確去除。"""
        wrapped = "  ```json\n{\"key\": \"value\"}\n```  "
        result = _strip_markdown_fences(wrapped)
        assert result == '{"key": "value"}'


# ---------------------------------------------------------------
# _build_retry_prompt 單元測試
# ---------------------------------------------------------------

class TestBuildRetryPrompt:
    """測試 retry prompt 組合輔助函式。"""

    def test_contains_error_message(self) -> None:
        """retry prompt 必須包含錯誤訊息。"""
        prompt = _build_retry_prompt("JSON 解析失敗：xxx", "原始輸入")
        assert "JSON 解析失敗：xxx" in prompt

    def test_contains_original_input(self) -> None:
        """retry prompt 必須包含原始輸入。"""
        prompt = _build_retry_prompt("某個錯誤", "使用者的原始輸入文字")
        assert "使用者的原始輸入文字" in prompt

    def test_contains_schema(self) -> None:
        """retry prompt 必須包含 JSON Schema。"""
        prompt = _build_retry_prompt("某個錯誤", "原始輸入")
        # Presentation 的 JSON Schema 一定包含 presentation_title
        assert "presentation_title" in prompt


# ---------------------------------------------------------------
# validate_and_retry 整合測試
# ---------------------------------------------------------------

class TestValidateAndRetry:
    """測試 validate_and_retry 主流程。"""

    def test_success_on_first_attempt(self) -> None:
        """一次成功：AI 輸出合法 JSON，直接通過驗證。"""
        mock_client = _make_mock_client()
        result = validate_and_retry(
            raw_output=VALID_JSON_STR,
            original_input="業務說明文字",
            llm_client=mock_client,
        )

        # 驗證結果型別正確
        assert isinstance(result, Presentation)
        assert result.presentation_title == "測試簡報"

        # 不應呼叫 LLM
        mock_client.generate.assert_not_called()

    def test_success_with_markdown_fence(self) -> None:
        """markdown code block 去除：AI 輸出被 ```json ``` 包裝，應自動去除後解析成功。"""
        wrapped_output = f"```json\n{VALID_JSON_STR}\n```"
        mock_client = _make_mock_client()

        result = validate_and_retry(
            raw_output=wrapped_output,
            original_input="業務說明文字",
            llm_client=mock_client,
        )

        assert isinstance(result, Presentation)
        # 不應呼叫 LLM
        mock_client.generate.assert_not_called()

    def test_retry_after_json_parse_failure(self) -> None:
        """JSON 解析失敗後 retry 成功：第一次輸出非法 JSON，retry 後成功。"""
        # 第一次 retry 回傳合法 JSON
        mock_client = _make_mock_client(VALID_JSON_STR)

        result = validate_and_retry(
            raw_output=INVALID_JSON_STR,
            original_input="業務說明文字",
            llm_client=mock_client,
            max_retries=3,
        )

        assert isinstance(result, Presentation)

        # 應呼叫 LLM 一次（第一次 retry）
        assert mock_client.generate.call_count == 1

    def test_retry_after_pydantic_validation_failure(self) -> None:
        """Pydantic 驗證失敗後 retry 成功：JSON 合法但欄位不對，retry 後成功。"""
        # 第一次 retry 回傳通過 Pydantic 驗證的 JSON
        mock_client = _make_mock_client(VALID_JSON_STR)

        result = validate_and_retry(
            raw_output=INVALID_PYDANTIC_STR,
            original_input="業務說明文字",
            llm_client=mock_client,
            max_retries=3,
        )

        assert isinstance(result, Presentation)
        assert mock_client.generate.call_count == 1

    def test_raises_after_exceeding_max_retries_json(self) -> None:
        """超過重試上限（JSON 失敗）：連續失敗超過 max_retries，拋出 ValueError。"""
        # 所有 retry 都回傳非法 JSON
        mock_client = _make_mock_client(
            INVALID_JSON_STR,
            INVALID_JSON_STR,
            INVALID_JSON_STR,
        )

        with pytest.raises(ValueError, match="超過重試上限"):
            validate_and_retry(
                raw_output=INVALID_JSON_STR,
                original_input="業務說明文字",
                llm_client=mock_client,
                max_retries=3,
            )

        # 應呼叫 LLM 3 次（max_retries = 3）
        assert mock_client.generate.call_count == 3

    def test_raises_after_exceeding_max_retries_pydantic(self) -> None:
        """超過重試上限（Pydantic 失敗）：連續失敗超過 max_retries，拋出 ValidationError。"""
        # 所有 retry 都回傳 Pydantic 驗證失敗的 JSON
        mock_client = _make_mock_client(
            INVALID_PYDANTIC_STR,
            INVALID_PYDANTIC_STR,
            INVALID_PYDANTIC_STR,
        )

        with pytest.raises(ValidationError):
            validate_and_retry(
                raw_output=INVALID_PYDANTIC_STR,
                original_input="業務說明文字",
                llm_client=mock_client,
                max_retries=3,
            )

        # 應呼叫 LLM 3 次
        assert mock_client.generate.call_count == 3

    def test_retry_prompt_contains_error_message(self) -> None:
        """retry prompt 包含錯誤訊息：驗證 retry 時呼叫 LLM 的 prompt 包含上次的錯誤訊息。"""
        # 第一次回傳合法 JSON（避免無限 retry）
        mock_client = _make_mock_client(VALID_JSON_STR)

        validate_and_retry(
            raw_output=INVALID_JSON_STR,
            original_input="業務說明文字",
            llm_client=mock_client,
            max_retries=3,
        )

        # 取得 LLM 被呼叫時的 prompt
        actual_prompt = mock_client.generate.call_args[0][0]

        # 驗證 prompt 包含錯誤訊息的關鍵字
        assert "JSON 解析失敗" in actual_prompt or "Expecting" in actual_prompt

    def test_retry_prompt_contains_original_input(self) -> None:
        """retry prompt 必須包含原始輸入文字。"""
        mock_client = _make_mock_client(VALID_JSON_STR)
        original_input = "這是一段獨特的業務說明文字 UNIQUE_INPUT_XYZ"

        validate_and_retry(
            raw_output=INVALID_JSON_STR,
            original_input=original_input,
            llm_client=mock_client,
            max_retries=3,
        )

        actual_prompt = mock_client.generate.call_args[0][0]
        assert original_input in actual_prompt

    def test_max_retries_zero_raises_immediately(self) -> None:
        """max_retries=0 時，第一次失敗即拋出例外，不呼叫 LLM。"""
        mock_client = _make_mock_client()

        with pytest.raises((ValueError, ValidationError)):
            validate_and_retry(
                raw_output=INVALID_JSON_STR,
                original_input="業務說明文字",
                llm_client=mock_client,
                max_retries=0,
            )

        # max_retries=0 不應呼叫 LLM
        mock_client.generate.assert_not_called()
