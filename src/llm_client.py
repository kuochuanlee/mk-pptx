"""
LLM 呼叫抽象層。

設計目的：將 AI 呼叫邏輯與業務邏輯解耦，
支援在不同環境（家用 / 公司）透過環境變數 LLM_BACKEND 切換不同 backend。

支援的 backend：
  - gemini：Google Gemini API，需設定 GEMINI_API_KEY
  - azure_openai：Azure OpenAI，需設定 AZURE_OPENAI_ENDPOINT 與 AZURE_OPENAI_KEY
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# 預設逾時秒數
DEFAULT_TIMEOUT_SECONDS = 60


class LLMClient(ABC):
    """LLM 呼叫統一介面（抽象基底類別）。"""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """傳入 prompt，回傳 LLM 純文字回應。"""
        ...


class GeminiClient(LLMClient):
    """Google Gemini API 實作（家用開發環境）。"""

    def __init__(self) -> None:
        # 從環境變數讀取 API key，禁止寫死
        api_key = os.environ.get("GEMINI_API_KEY")

        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY 未設定。"
                "請在 .env 檔案或環境變數中設定 GEMINI_API_KEY。"
            )

        # 延遲 import，未安裝 SDK 時不影響其他模組的匯入
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError(
                "google-generativeai 套件未安裝。"
                "請執行：uv pip install google-generativeai"
            ) from exc

        genai.configure(api_key=api_key)

        # 使用 gemini-2.0-flash 作為預設模型
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self._model = genai.GenerativeModel(model_name)

        logger.info("GeminiClient 初始化完成，模型：%s", model_name)

    def generate(self, prompt: str) -> str:
        """呼叫 Gemini API 並回傳純文字回應。"""
        import socket

        try:
            response = self._model.generate_content(
                prompt,
                request_options={"timeout": DEFAULT_TIMEOUT_SECONDS},
            )
            return response.text

        except Exception as exc:
            error_msg = str(exc)

            # 判斷是否為 API key 過期或無效的錯誤
            if "API_KEY_INVALID" in error_msg or "API key not valid" in error_msg:
                raise PermissionError(
                    "GEMINI_API_KEY 無效或已過期。"
                    "請重新取得有效的 API key 並更新 .env 檔案。"
                ) from exc

            # 判斷是否為網路連線問題
            if isinstance(exc.__cause__, (ConnectionError, socket.gaierror)):
                logger.error("網路連線失敗：%s", error_msg)
                raise ConnectionError(
                    f"無法連線至 Gemini API：{error_msg}"
                ) from exc

            # 判斷是否為逾時
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                raise TimeoutError(
                    f"Gemini API 呼叫逾時（超過 {DEFAULT_TIMEOUT_SECONDS} 秒）。"
                ) from exc

            # 其他未知錯誤，記錄 log 後重新拋出
            logger.error("Gemini API 呼叫失敗：%s", error_msg)
            raise


class AzureOpenAIClient(LLMClient):
    """Azure OpenAI 實作（公司環境）。

    注意：公司 API key 每 7 天過期，需定期重新申請。
    """

    def __init__(self) -> None:
        # 從環境變數讀取必要設定，禁止寫死
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        api_key = os.environ.get("AZURE_OPENAI_KEY")

        if not endpoint:
            raise EnvironmentError(
                "AZURE_OPENAI_ENDPOINT 未設定。"
                "請在 .env 檔案或環境變數中設定 AZURE_OPENAI_ENDPOINT。"
            )

        if not api_key:
            raise EnvironmentError(
                "AZURE_OPENAI_KEY 未設定。"
                "請在 .env 檔案或環境變數中設定 AZURE_OPENAI_KEY。"
                "注意：公司 API key 每 7 天過期，需定期重新申請。"
            )

        # 部署名稱（deployment），預設 gpt-4o
        self._deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

        # 延遲 import，未安裝 SDK 時不影響其他模組的匯入
        try:
            from openai import AzureOpenAI
        except ImportError as exc:
            raise ImportError(
                "openai 套件未安裝。"
                "請執行：uv pip install openai"
            ) from exc

        self._client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version="2024-02-01",
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )

        logger.info(
            "AzureOpenAIClient 初始化完成，endpoint：%s，deployment：%s",
            endpoint,
            self._deployment,
        )

    def generate(self, prompt: str) -> str:
        """呼叫 Azure OpenAI API 並回傳純文字回應。"""
        import socket

        try:
            response = self._client.chat.completions.create(
                model=self._deployment,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content or ""

        except Exception as exc:
            error_msg = str(exc)

            # 判斷是否為 API key 過期或無效的錯誤（HTTP 401）
            if "401" in error_msg or "AuthenticationFailed" in error_msg:
                raise PermissionError(
                    "AZURE_OPENAI_KEY 無效或已過期。"
                    "公司 API key 每 7 天過期，請重新申請並更新 .env 檔案。"
                ) from exc

            # 判斷是否為網路連線問題
            if isinstance(exc.__cause__, (ConnectionError, socket.gaierror)):
                logger.error("網路連線失敗：%s", error_msg)
                raise ConnectionError(
                    f"無法連線至 Azure OpenAI API：{error_msg}"
                ) from exc

            # 判斷是否為逾時
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                raise TimeoutError(
                    f"Azure OpenAI API 呼叫逾時（超過 {DEFAULT_TIMEOUT_SECONDS} 秒）。"
                ) from exc

            # 其他未知錯誤，記錄 log 後重新拋出
            logger.error("Azure OpenAI API 呼叫失敗：%s", error_msg)
            raise


def create_client() -> LLMClient:
    """LLM Client Factory：依 LLM_BACKEND 環境變數建立對應的 client 實例。

    支援的 backend 值：
      - gemini（預設）：使用 Google Gemini API
      - azure_openai：使用 Azure OpenAI API

    Returns:
        LLMClient 實例

    Raises:
        ValueError: 若 LLM_BACKEND 為不支援的值
        EnvironmentError: 若必要的環境變數未設定
    """
    backend = os.environ.get("LLM_BACKEND", "gemini").lower().strip()

    if backend == "gemini":
        return GeminiClient()

    if backend == "azure_openai":
        return AzureOpenAIClient()

    raise ValueError(
        f"不支援的 LLM_BACKEND 值：'{backend}'。"
        "目前支援：gemini、azure_openai。"
        "請檢查 .env 檔案中的 LLM_BACKEND 設定。"
    )
