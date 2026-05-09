"""
JSON 驗證與 retry 邏輯模組。

負責將 LLM 輸出的原始字串解析成合法的 Presentation 物件，
若解析或驗證失敗，會自動組成 retry prompt 並重新呼叫 LLM，
直到成功或超過重試上限為止。
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from schemas.slide_schema import Presentation
from src.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _strip_markdown_fences(text: str) -> str:
    """去除 AI 輸出中常見的 markdown code block 包裝。

    Args:
        text: AI 回傳的原始字串，可能包含 ```json ... ``` 或 ``` ... ```

    Returns:
        去除包裝後的純文字字串
    """
    # 嘗試匹配 ```json ... ``` 或 ``` ... ``` 格式
    pattern = r"```(?:json)?\s*\n?([\s\S]*?)```"
    match = re.search(pattern, text.strip())

    if match:
        return match.group(1).strip()

    return text.strip()


def _build_retry_prompt(
    error_message: str,
    original_input: str,
) -> str:
    """組合 retry prompt，讓 LLM 依據錯誤訊息重新輸出合法 JSON。

    Args:
        error_message: 上次驗證失敗的錯誤訊息
        original_input: 使用者的原始輸入文字

    Returns:
        組合好的 retry prompt 字串
    """
    # 取得 Presentation 的完整 JSON Schema 定義
    schema_definition = json.dumps(
        Presentation.model_json_schema(),
        ensure_ascii=False,
        indent=2,
    )

    prompt = (
        "上一次輸出的 JSON 格式有誤，錯誤訊息如下：\n"
        f"{error_message}\n\n"
        "請嚴格按照以下 Schema 重新輸出，只輸出 JSON，不要有任何其他文字：\n"
        f"{schema_definition}\n\n"
        "原始輸入內容：\n"
        f"{original_input}"
    )

    return prompt


def validate_and_retry(
    raw_output: str,
    original_input: str,
    llm_client: LLMClient,
    max_retries: int = 3,
) -> Presentation:
    """驗證 AI 輸出的 JSON 並在失敗時自動 retry。

    Args:
        raw_output: AI 輸出的原始字串（應為 JSON）
        original_input: 使用者的原始輸入文字（retry 時需要）
        llm_client: LLM 呼叫介面
        max_retries: 最大重試次數（預設 3）

    Returns:
        驗證通過的 Presentation 物件

    Raises:
        ValidationError: 超過重試上限後仍無法通過驗證時拋出最後一次的錯誤
        ValueError: 超過重試上限後仍無法解析 JSON 時拋出
    """
    current_output = raw_output
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        # 記錄本次嘗試資訊
        if attempt == 0:
            logger.info("開始驗證 LLM 輸出（原始輸出長度：%d 字元）", len(current_output))
        else:
            logger.info(
                "第 %d 次 retry（共最多 %d 次）",
                attempt,
                max_retries,
            )

        # 步驟一：去除 markdown code block 包裝
        cleaned = _strip_markdown_fences(current_output)
        logger.debug("清理後輸出（前 200 字元）：%s", cleaned[:200])

        # 步驟二：嘗試 JSON 解析
        try:
            parsed_dict = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            last_error = exc
            error_message = f"JSON 解析失敗：{exc}"

            logger.warning(
                "嘗試 %d/%d：JSON 解析失敗。原始輸出（前 500 字元）：%s\n錯誤：%s",
                attempt + 1,
                max_retries + 1,
                current_output[:500],
                exc,
            )

            # 已達重試上限，跳出迴圈
            if attempt >= max_retries:
                break

            # 組成 retry prompt 並重新呼叫 LLM
            retry_prompt = _build_retry_prompt(error_message, original_input)
            current_output = llm_client.generate(retry_prompt)
            continue

        # 步驟三：嘗試 Pydantic 驗證
        try:
            presentation = Presentation.model_validate(parsed_dict)
            logger.info("驗證成功（嘗試 %d 次）", attempt + 1)
            return presentation

        except ValidationError as exc:
            last_error = exc
            error_message = f"Pydantic 驗證失敗：{exc}"

            logger.warning(
                "嘗試 %d/%d：Pydantic 驗證失敗。\n錯誤：%s",
                attempt + 1,
                max_retries + 1,
                exc,
            )

            # 已達重試上限，跳出迴圈
            if attempt >= max_retries:
                break

            # 組成 retry prompt 並重新呼叫 LLM
            retry_prompt = _build_retry_prompt(error_message, original_input)
            current_output = llm_client.generate(retry_prompt)

    # 超過重試上限，記錄完整 log 後拋出例外
    logger.error(
        "超過重試上限（%d 次），驗證仍然失敗。\n"
        "原始輸入（前 500 字元）：%s\n"
        "最後一次 LLM 輸出（前 500 字元）：%s\n"
        "最後一次錯誤：%s",
        max_retries,
        original_input[:500],
        current_output[:500],
        last_error,
    )

    # 根據最後一次錯誤類型決定拋出哪種例外
    if isinstance(last_error, ValidationError):
        raise last_error

    raise ValueError(
        f"超過重試上限（{max_retries} 次），JSON 驗證仍然失敗。\n"
        f"原始輸入：{original_input}\n"
        f"最後一次 LLM 輸出：{current_output}\n"
        f"最後一次錯誤：{last_error}"
    )
