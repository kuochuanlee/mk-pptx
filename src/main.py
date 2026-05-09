"""
CLI 統一入口（src/main.py）。

支援三種操作模式：
  1. 文字稿 -> PPTX（完整流程）
     python -m src.main --input input/briefing.txt --output output/report.pptx

  2. 從現有 JSON 直接生成 PPTX（跳過 AI 步驟）
     python -m src.main --json input/slides.json --output output/report.pptx

  3. 只生成 Mermaid 圖表（輸出 PNG + SVG）
     python -m src.main --diagram input/flow.mmd --output output/flow.png

執行順序（模式一）：
  1. 載入 .env 環境變數
  2. 讀取輸入文字 + 載入 SKILL prompt
  3. 初始化 LLMClient（依 LLM_BACKEND 環境變數決定 backend）
  4. 呼叫 LLM 生成 JSON（使用 json_outline SKILL）
  5. validate.py 驗證 JSON（含 auto-retry）
  6. build_pptx.py 組裝 PPTX
  7. 輸出至 output/ 目錄
  8. 印出完成訊息（共幾頁、耗時、輸出路徑）
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# 載入 .env 環境變數（必須在其他 import 之前執行）
from dotenv import load_dotenv

load_dotenv()

from src.llm_client import create_client
from src.validate import validate_and_retry
from src.build_pptx import build_pptx
from src.build_diagram import build_diagram
from schemas.slide_schema import Presentation

# 設定 logging 格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

# SKILL prompt 路徑（相對於專案根目錄）
SKILL_JSON_OUTLINE_PATH = Path("skills") / "json-outline" / "SKILL.md"

# template_map.json 路徑
TEMPLATE_MAP_PATH = Path("config") / "template_map.json"

# mmdc 設定檔路徑
MERMAID_CONFIG_PATH = Path("config") / "mermaid.json"

# 圖表輸出目錄
DIAGRAM_OUTPUT_DIR = Path("output")


def _load_skill_prompt(skill_path: Path) -> str:
    """載入 SKILL prompt 並回傳純文字內容。

    Args:
        skill_path: SKILL Markdown 檔案路徑

    Returns:
        SKILL prompt 字串

    Raises:
        FileNotFoundError: SKILL 檔案不存在
    """
    if not skill_path.exists():
        raise FileNotFoundError(
            f"SKILL prompt 檔案不存在：{skill_path}\n"
            "請確認 skills/ 目錄下有對應的 Markdown 檔案。"
        )

    return skill_path.read_text(encoding="utf-8")


def _build_outline_prompt(skill_prompt: str, user_input: str) -> str:
    """將 SKILL prompt 與使用者輸入組合成完整的 LLM prompt。

    SKILL prompt 最後一行格式為：
      請將以下內容轉換為簡報 JSON：
      {USER_INPUT}

    Args:
        skill_prompt: 完整的 SKILL prompt 文字
        user_input: 使用者的輸入文字（文字稿內容）

    Returns:
        組合完成的 LLM prompt 字串
    """
    return skill_prompt.replace("{USER_INPUT}", user_input)


def _run_full_pipeline(
    input_path: Path,
    output_path: Path,
) -> None:
    """執行完整流程：文字稿 -> LLM -> validate -> PPTX。

    Args:
        input_path: 輸入文字稿路徑
        output_path: 輸出 .pptx 路徑
    """
    start_time = time.time()

    # 步驟一：讀取輸入文字
    if not input_path.exists():
        print(f"[錯誤] 輸入檔案不存在：{input_path}", file=sys.stderr)
        sys.exit(1)

    user_input = input_path.read_text(encoding="utf-8").strip()
    logger.info("已讀取輸入文字（%d 字元）：%s", len(user_input), input_path)

    # 步驟二：載入 SKILL prompt
    skill_prompt = _load_skill_prompt(SKILL_JSON_OUTLINE_PATH)
    full_prompt = _build_outline_prompt(skill_prompt, user_input)
    logger.info("已載入 SKILL prompt：%s", SKILL_JSON_OUTLINE_PATH)

    # 步驟三：初始化 LLMClient
    print("[1/4] 初始化 LLM Client...")
    try:
        llm_client = create_client()
    except (EnvironmentError, ValueError) as exc:
        print(f"[錯誤] LLM Client 初始化失敗：{exc}", file=sys.stderr)
        sys.exit(1)

    # 步驟四：呼叫 LLM 生成 JSON
    print("[2/4] 呼叫 AI 生成簡報結構...")
    try:
        raw_output = llm_client.generate(full_prompt)
    except PermissionError as exc:
        print(f"[錯誤] API Key 無效或已過期：{exc}", file=sys.stderr)
        sys.exit(1)
    except (ConnectionError, TimeoutError) as exc:
        print(f"[錯誤] 網路或逾時問題：{exc}", file=sys.stderr)
        sys.exit(1)

    logger.info("LLM 回應長度：%d 字元", len(raw_output))

    # 步驟五：驗證 JSON（含 auto-retry）
    print("[3/4] 驗證 JSON 結構...")
    try:
        presentation_data = validate_and_retry(
            raw_output=raw_output,
            original_input=user_input,
            llm_client=llm_client,
        )
    except Exception as exc:
        print(f"[錯誤] JSON 驗證失敗（超過重試上限）：{exc}", file=sys.stderr)
        sys.exit(1)

    # 步驟六：組裝 PPTX
    _assemble_and_save_pptx(presentation_data, output_path, start_time)


def _run_from_json(
    json_path: Path,
    output_path: Path,
) -> None:
    """從現有 JSON 直接生成 PPTX（跳過 AI 步驟）。

    Args:
        json_path: 輸入 JSON 檔路徑
        output_path: 輸出 .pptx 路徑
    """
    start_time = time.time()

    # 讀取並解析 JSON
    if not json_path.exists():
        print(f"[錯誤] JSON 檔案不存在：{json_path}", file=sys.stderr)
        sys.exit(1)

    print("[1/2] 讀取並驗證 JSON...")
    try:
        raw_json = json_path.read_text(encoding="utf-8")
        parsed_dict = json.loads(raw_json)
        presentation_data = Presentation.model_validate(parsed_dict)
    except json.JSONDecodeError as exc:
        print(f"[錯誤] JSON 格式錯誤：{exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[錯誤] JSON Schema 驗證失敗：{exc}", file=sys.stderr)
        sys.exit(1)

    logger.info("已載入 JSON（%d 頁）：%s", len(presentation_data.slides), json_path)

    # 組裝 PPTX
    print("[2/2] 組裝 PPTX...")
    _assemble_and_save_pptx(presentation_data, output_path, start_time)


def _run_diagram_only(
    diagram_path: Path,
    output_path: Path,
) -> None:
    """只生成 Mermaid 圖表（輸出 PNG + SVG）。

    Args:
        diagram_path: 輸入 .mmd 檔路徑
        output_path: 輸出 PNG 路徑（SVG 同名自動產生）
    """
    start_time = time.time()

    # 讀取 .mmd 檔
    if not diagram_path.exists():
        print(f"[錯誤] 圖表檔案不存在：{diagram_path}", file=sys.stderr)
        sys.exit(1)

    mermaid_string = diagram_path.read_text(encoding="utf-8").strip()
    logger.info("已讀取 mermaid 檔案（%d 字元）：%s", len(mermaid_string), diagram_path)

    # 決定輸出目錄和主檔名
    output_dir = output_path.parent
    output_stem = output_path.stem

    print(f"[1/1] 渲染 Mermaid 圖表：{diagram_path.name}...")
    result = build_diagram(
        mermaid_string=mermaid_string,
        output_stem=output_stem,
        output_dir=output_dir,
        config_path=MERMAID_CONFIG_PATH,
    )

    if result is None:
        print("[錯誤] 圖表渲染失敗，請確認 mmdc 已安裝。", file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - start_time

    print()
    print("完成！")
    print(f"  PNG 路徑：{result.png_path}")
    print(f"  SVG 路徑：{result.svg_path}")
    print(f"  耗時：{elapsed:.1f} 秒")


def _assemble_and_save_pptx(
    presentation_data: Presentation,
    output_path: Path,
    start_time: float,
) -> None:
    """組裝 PPTX 並印出完成訊息。

    Args:
        presentation_data: 已驗證的 Presentation 物件
        output_path: 輸出 .pptx 路徑
        start_time: 流程開始時間（time.time()）
    """
    # 確保輸出目錄存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        result_path = build_pptx(
            presentation_data=presentation_data,
            output_path=output_path,
            template_map_path=TEMPLATE_MAP_PATH,
        )
    except FileNotFoundError as exc:
        print(f"[錯誤] 模板檔案或設定檔不存在：{exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[錯誤] PPTX 組裝失敗：{exc}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - start_time
    slide_count = len(presentation_data.slides)

    print()
    print("完成！")
    print(f"  簡報標題：{presentation_data.presentation_title}")
    print(f"  共 {slide_count} 頁")
    print(f"  輸出路徑：{result_path}")
    print(f"  耗時：{elapsed:.1f} 秒")


def _build_arg_parser() -> argparse.ArgumentParser:
    """建立並回傳 CLI argument parser。

    Returns:
        設定完成的 ArgumentParser 物件
    """
    parser = argparse.ArgumentParser(
        prog="mk-pptx",
        description="AI 輔助企業簡報自動化工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "使用範例：\n"
            "  # 完整流程：文字稿 -> PPTX\n"
            "  python -m src.main --input input/briefing.txt --output output/report.pptx\n\n"
            "  # 從現有 JSON 直接生成 PPTX\n"
            "  python -m src.main --json input/slides.json --output output/report.pptx\n\n"
            "  # 只生成 Mermaid 圖表\n"
            "  python -m src.main --diagram input/flow.mmd --output output/flow.png\n"
        ),
    )

    # 三個互斥的操作模式
    mode_group = parser.add_mutually_exclusive_group(required=True)

    mode_group.add_argument(
        "--input",
        metavar="FILE",
        type=Path,
        help="輸入文字稿路徑（完整流程：文字 -> AI -> PPTX）",
    )

    mode_group.add_argument(
        "--json",
        metavar="FILE",
        type=Path,
        dest="json_file",
        help="輸入 JSON 檔案路徑（跳過 AI，直接從 JSON 生成 PPTX）",
    )

    mode_group.add_argument(
        "--diagram",
        metavar="FILE",
        type=Path,
        help="輸入 Mermaid .mmd 檔路徑（只生成圖表，輸出 PNG + SVG）",
    )

    # 輸出路徑（三種模式共用）
    parser.add_argument(
        "--output",
        "-o",
        metavar="FILE",
        type=Path,
        required=True,
        help="輸出檔案路徑（.pptx 或 .png）",
    )

    # 可選：指定 template_map.json 路徑
    parser.add_argument(
        "--template-map",
        metavar="FILE",
        type=Path,
        default=None,
        help=f"template_map.json 路徑（預設：{TEMPLATE_MAP_PATH}）",
    )

    # 可選：調整 log 等級
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="啟用詳細 log 輸出（DEBUG 等級）",
    )

    return parser


def main() -> None:
    """CLI 主入口函式。

    解析命令列參數並分派至對應的處理函式。
    """
    parser = _build_arg_parser()
    args = parser.parse_args()

    # 設定 log 等級
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("已啟用詳細 log 輸出")

    # 若使用者有指定 template_map，覆蓋全域設定
    if args.template_map is not None:
        global TEMPLATE_MAP_PATH
        TEMPLATE_MAP_PATH = args.template_map

    # 依操作模式分派
    if args.input is not None:
        _run_full_pipeline(
            input_path=args.input,
            output_path=args.output,
        )

    elif args.json_file is not None:
        _run_from_json(
            json_path=args.json_file,
            output_path=args.output,
        )

    elif args.diagram is not None:
        _run_diagram_only(
            diagram_path=args.diagram,
            output_path=args.output,
        )


if __name__ == "__main__":
    main()
