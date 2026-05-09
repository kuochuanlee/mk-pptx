"""
Mermaid 圖表渲染模組。

將 mermaid string 轉換為 PNG 和 SVG 檔案，供 build_pptx.py 使用。

處理邏輯：
  1. 從 JSON content.mermaid 欄位讀取 mermaid string
  2. 寫入暫存 .mmd 檔（真正換行）
  3. 呼叫 mmdc CLI，同時輸出 .svg（母檔）和 .png（供 python-pptx 插入）
  4. 回傳 DiagramResult（包含 png_path、svg_path）
  5. 清理暫存 .mmd 檔

錯誤處理：
  - mmdc 執行失敗（exit code != 0）-> 記錄 stderr log，回傳 None，上層 fallback 至 bullets_only
  - 不因單一圖表失敗中斷整份簡報
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# mmdc 指令名稱（全域安裝時直接呼叫）
MMDC_COMMAND = "mmdc"

# PNG 輸出的縮放倍率（3 倍確保高解析度供 PPTX 使用）
PNG_SCALE = 3

# mmdc 執行逾時秒數
MMDC_TIMEOUT_SECONDS = 60

# mmdc 設定檔預設路徑（相對於專案根目錄）
DEFAULT_CONFIG_PATH = Path("config") / "mermaid.json"


@dataclass
class DiagramResult:
    """圖表渲染結果，包含 PNG 和 SVG 的輸出路徑。"""

    # PNG 路徑（供 python-pptx 插入）
    png_path: Path

    # SVG 路徑（母檔，供手動微調）
    svg_path: Path


def _find_mmdc() -> str | None:
    """尋找 mmdc 可執行檔。

    優先順序：
      1. 環境變數 MMDC_PATH 指定的路徑
      2. PATH 中的 mmdc 指令

    Returns:
        mmdc 路徑字串，若找不到則回傳 None
    """
    # 優先使用環境變數指定的路徑
    env_path = os.environ.get("MMDC_PATH")

    if env_path:
        if Path(env_path).is_file():
            return env_path

        logger.warning("MMDC_PATH 指定的路徑不存在：%s", env_path)

    # 嘗試用 where（Windows）或 which（Unix）在 PATH 中尋找
    import shutil

    mmdc_path = shutil.which(MMDC_COMMAND)

    return mmdc_path


def is_mmdc_available() -> bool:
    """檢查 mmdc 是否可用。

    供測試的 skip 條件和外部呼叫使用。

    Returns:
        True 表示 mmdc 可執行，False 表示不可用
    """
    return _find_mmdc() is not None


def build_diagram(
    mermaid_string: str,
    output_stem: str,
    output_dir: Path,
    config_path: Path | None = None,
) -> DiagramResult | None:
    """將 mermaid string 渲染為 PNG 和 SVG。

    Args:
        mermaid_string: mermaid 語法字串（可含字面 \\n 或真正換行）
        output_stem: 輸出檔案主檔名（不含副檔名），例如 "slide_3_diagram"
        output_dir: 輸出目錄 Path 物件
        config_path: mmdc 設定檔路徑（None 時使用預設的 config/mermaid.json）

    Returns:
        DiagramResult（包含 png_path 和 svg_path），
        若 mmdc 執行失敗則回傳 None（上層應 fallback 至 bullets_only）
    """
    # 確認 mmdc 可用
    mmdc_exe = _find_mmdc()

    if mmdc_exe is None:
        logger.error(
            "找不到 mmdc 指令。請確認已安裝 @mermaid-js/mermaid-cli，"
            "或設定環境變數 MMDC_PATH 指向 mmdc 可執行檔。"
        )
        return None

    # 確認輸出目錄存在
    output_dir.mkdir(parents=True, exist_ok=True)

    # 決定 mmdc 設定檔路徑
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    # 定義輸出路徑
    png_path = output_dir / f"{output_stem}.png"
    svg_path = output_dir / f"{output_stem}.svg"

    # 將 mermaid string 寫入暫存 .mmd 檔
    # 使用 NamedTemporaryFile 確保清理，delete=False 讓 mmdc 可讀取
    tmp_mmd: Path | None = None

    try:
        tmp_mmd = _write_temp_mmd(mermaid_string)

        # 渲染 PNG
        png_success = _run_mmdc(
            mmdc_exe=mmdc_exe,
            input_path=tmp_mmd,
            output_path=png_path,
            config_path=config_path,
            scale=PNG_SCALE,
        )

        if not png_success:
            return None

        # 渲染 SVG
        svg_success = _run_mmdc(
            mmdc_exe=mmdc_exe,
            input_path=tmp_mmd,
            output_path=svg_path,
            config_path=config_path,
            scale=None,
        )

        if not svg_success:
            return None

        logger.info(
            "圖表渲染完成：PNG=%s，SVG=%s",
            png_path,
            svg_path,
        )

        return DiagramResult(png_path=png_path, svg_path=svg_path)

    finally:
        # 無論成功或失敗，都清理暫存 .mmd 檔
        if tmp_mmd is not None and tmp_mmd.exists():
            tmp_mmd.unlink()
            logger.debug("已清理暫存檔：%s", tmp_mmd)


def _write_temp_mmd(mermaid_string: str) -> Path:
    """將 mermaid string 寫入暫存 .mmd 檔並回傳路徑。

    字面上的 \\n 會還原為真正的換行，確保 mmdc 可正確解析。

    Args:
        mermaid_string: mermaid 語法字串

    Returns:
        暫存 .mmd 檔的 Path
    """
    # 還原字面 \n 為真正的換行（JSON 中常以 \n 儲存）
    content = mermaid_string.replace("\\n", "\n")

    # suffix='.mmd' 確保 mmdc 能辨識格式
    # delete=False 讓後續程式可讀取檔案（Windows 限制）
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".mmd",
        encoding="utf-8",
        delete=False,
    ) as tmp:
        tmp.write(content)
        return Path(tmp.name)


def _run_mmdc(
    mmdc_exe: str,
    input_path: Path,
    output_path: Path,
    config_path: Path,
    scale: int | None,
) -> bool:
    """執行 mmdc 指令，渲染單一輸出格式。

    Args:
        mmdc_exe: mmdc 可執行檔路徑
        input_path: 輸入 .mmd 檔路徑
        output_path: 輸出檔案路徑（.png 或 .svg）
        config_path: mmdc 設定檔路徑
        scale: PNG 縮放倍率（None 表示 SVG，不傳 -s 參數）

    Returns:
        True 表示成功，False 表示失敗
    """
    # 組合 mmdc 指令參數
    cmd = [
        mmdc_exe,
        "-i", str(input_path),
        "-o", str(output_path),
    ]

    # 僅在設定檔存在時加入 -c 參數
    if config_path.exists():
        cmd.extend(["-c", str(config_path)])
    else:
        logger.warning("mmdc 設定檔不存在，使用 mmdc 預設樣式：%s", config_path)

    # PNG 模式才加入 -s 縮放參數
    if scale is not None:
        cmd.extend(["-s", str(scale)])

    logger.debug("執行 mmdc 指令：%s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=MMDC_TIMEOUT_SECONDS,
        )

        if result.returncode != 0:
            logger.error(
                "mmdc 執行失敗（exit code=%d），輸出：%s，stderr：%s",
                result.returncode,
                result.stdout.strip(),
                result.stderr.strip(),
            )
            return False

        return True

    except subprocess.TimeoutExpired:
        logger.error(
            "mmdc 執行逾時（超過 %d 秒），輸入檔：%s",
            MMDC_TIMEOUT_SECONDS,
            input_path,
        )
        return False

    except FileNotFoundError:
        logger.error("mmdc 執行檔不存在：%s", mmdc_exe)
        return False
