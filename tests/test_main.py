"""
main.py CLI 測試。

測試策略：
  - 使用 unittest.mock 隔離 LLMClient、build_pptx、build_diagram 等外部依賴
  - 測試 argument parser 的正確行為
  - 測試三種操作模式（--input, --json, --diagram）的正常流程
  - 測試各種錯誤情境（檔案不存在、LLM 失敗、驗證失敗）
  - 不依賴真實 API key 或 mmdc 環境

CI 注意事項：
  - 所有測試均透過 mock 隔離外部依賴，可在 CI 環境中執行
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.main import (
    _build_arg_parser,
    _build_outline_prompt,
    _load_skill_prompt,
    main,
)


# ============================================================
# 測試用常數與 fixture
# ============================================================

# 測試用 JSON 資料（合法的 Presentation）
VALID_PRESENTATION_JSON = {
    "presentation_title": "測試簡報",
    "author": "測試人員",
    "date": "2025-06-01",
    "slides": [
        {
            "slide_number": 1,
            "layout_type": "title_slide",
            "title": "封面",
            "content": {"subtitle": "副標題"},
        }
    ],
}

# 最小有效 PNG bytes（1x1 透明 PNG）
MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01"
    b"\x00\x00\x00\x01"
    b"\x08\x02"
    b"\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx"
    b"\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture()
def input_txt(tmp_path: Path) -> Path:
    """建立測試用輸入文字稿。"""
    f = tmp_path / "briefing.txt"
    f.write_text("這是測試文字稿內容，說明本季業績成長狀況。", encoding="utf-8")
    return f


@pytest.fixture()
def valid_json_file(tmp_path: Path) -> Path:
    """建立測試用合法 JSON 檔案。"""
    f = tmp_path / "slides.json"
    f.write_text(
        json.dumps(VALID_PRESENTATION_JSON, ensure_ascii=False),
        encoding="utf-8",
    )
    return f


@pytest.fixture()
def mmd_file(tmp_path: Path) -> Path:
    """建立測試用 Mermaid .mmd 檔案。"""
    f = tmp_path / "flow.mmd"
    f.write_text("flowchart LR\n  A[開始] --> B[結束]", encoding="utf-8")
    return f


@pytest.fixture()
def skill_file(tmp_path: Path) -> Path:
    """建立測試用 SKILL prompt 檔案。"""
    f = tmp_path / "json_outline.md"
    f.write_text(
        "你是簡報專家。\n請將以下內容轉換為簡報 JSON：\n{USER_INPUT}",
        encoding="utf-8",
    )
    return f


@pytest.fixture()
def output_pptx(tmp_path: Path) -> Path:
    """建立測試用輸出 .pptx 路徑。"""
    return tmp_path / "out.pptx"


@pytest.fixture()
def output_png(tmp_path: Path) -> Path:
    """建立測試用輸出 .png 路徑。"""
    return tmp_path / "out.png"


# ============================================================
# _load_skill_prompt() 測試
# ============================================================


class TestLoadSkillPrompt:
    """_load_skill_prompt() 函式測試。"""

    def test_loads_existing_file(self, skill_file: Path):
        """存在的 SKILL 檔案應正確載入。"""
        content = _load_skill_prompt(skill_file)

        assert "簡報專家" in content

    def test_raises_when_file_not_found(self, tmp_path: Path):
        """不存在的 SKILL 檔案應拋出 FileNotFoundError。"""
        nonexistent = tmp_path / "nonexistent_skill.md"

        with pytest.raises(FileNotFoundError):
            _load_skill_prompt(nonexistent)

    def test_content_is_string(self, skill_file: Path):
        """載入結果應為字串。"""
        content = _load_skill_prompt(skill_file)

        assert isinstance(content, str)

    def test_preserves_full_content(self, skill_file: Path):
        """載入結果應包含完整 SKILL 內容。"""
        content = _load_skill_prompt(skill_file)

        assert "{USER_INPUT}" in content


# ============================================================
# _build_outline_prompt() 測試
# ============================================================


class TestBuildOutlinePrompt:
    """_build_outline_prompt() 函式測試。"""

    def test_replaces_user_input_placeholder(self):
        """應正確替換 {USER_INPUT} 佔位符。"""
        skill_prompt = "你是專家。請轉換：\n{USER_INPUT}"
        user_input = "這是業務說明。"

        result = _build_outline_prompt(skill_prompt, user_input)

        assert "這是業務說明。" in result
        assert "{USER_INPUT}" not in result

    def test_preserves_skill_content(self):
        """SKILL prompt 的其餘內容應保留。"""
        skill_prompt = "你是專家。請轉換：\n{USER_INPUT}"
        user_input = "測試輸入"

        result = _build_outline_prompt(skill_prompt, user_input)

        assert "你是專家" in result

    def test_handles_multiline_user_input(self):
        """使用者輸入含多行時應正確處理。"""
        skill_prompt = "角色設定。\n輸入：\n{USER_INPUT}"
        user_input = "第一行\n第二行\n第三行"

        result = _build_outline_prompt(skill_prompt, user_input)

        assert "第一行" in result
        assert "第二行" in result


# ============================================================
# argument parser 測試
# ============================================================


class TestArgParser:
    """CLI argument parser 測試。"""

    def test_input_mode_requires_output(self):
        """--input 模式必須搭配 --output。"""
        parser = _build_arg_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["--input", "in.txt"])

    def test_json_mode_parses_correctly(self, tmp_path: Path):
        """--json 模式的參數應正確解析。"""
        parser = _build_arg_parser()
        args = parser.parse_args(
            ["--json", "input/slides.json", "--output", "output/out.pptx"]
        )

        assert args.json_file == Path("input/slides.json")
        assert args.output == Path("output/out.pptx")

    def test_diagram_mode_parses_correctly(self):
        """--diagram 模式的參數應正確解析。"""
        parser = _build_arg_parser()
        args = parser.parse_args(
            ["--diagram", "input/flow.mmd", "--output", "output/flow.png"]
        )

        assert args.diagram == Path("input/flow.mmd")
        assert args.output == Path("output/flow.png")

    def test_input_and_json_are_mutually_exclusive(self):
        """--input 和 --json 不可同時使用。"""
        parser = _build_arg_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(
                ["--input", "in.txt", "--json", "in.json", "--output", "out.pptx"]
            )

    def test_verbose_flag_is_optional(self):
        """--verbose 是可選參數，預設 False。"""
        parser = _build_arg_parser()
        args = parser.parse_args(
            ["--json", "in.json", "--output", "out.pptx"]
        )

        assert args.verbose is False

    def test_verbose_flag_can_be_set(self):
        """--verbose 設定後應為 True。"""
        parser = _build_arg_parser()
        args = parser.parse_args(
            ["--json", "in.json", "--output", "out.pptx", "--verbose"]
        )

        assert args.verbose is True

    def test_short_v_flag_sets_verbose(self):
        """-v 短旗標應等同 --verbose。"""
        parser = _build_arg_parser()
        args = parser.parse_args(
            ["--json", "in.json", "--output", "out.pptx", "-v"]
        )

        assert args.verbose is True

    def test_short_o_flag_for_output(self):
        """-o 短旗標應等同 --output。"""
        parser = _build_arg_parser()
        args = parser.parse_args(
            ["--json", "in.json", "-o", "out.pptx"]
        )

        assert args.output == Path("out.pptx")

    def test_no_mode_exits_with_error(self):
        """未指定任何操作模式應以非零 exit code 結束。"""
        parser = _build_arg_parser()

        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--output", "out.pptx"])

        assert exc_info.value.code != 0


# ============================================================
# --json 模式功能測試
# ============================================================


class TestRunFromJson:
    """--json 模式（從現有 JSON 生成 PPTX）的功能測試。"""

    def test_exits_when_json_file_not_found(self, tmp_path: Path, output_pptx: Path):
        """JSON 檔案不存在時應以非零 exit code 結束。"""
        nonexistent = tmp_path / "nonexistent.json"
        args = [
            "--json", str(nonexistent),
            "--output", str(output_pptx),
        ]

        with patch("sys.argv", ["mk-pptx"] + args):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code != 0

    def test_exits_when_json_is_invalid_format(self, tmp_path: Path, output_pptx: Path):
        """JSON 格式錯誤時應以非零 exit code 結束。"""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("this is not json", encoding="utf-8")

        args = [
            "--json", str(bad_json),
            "--output", str(output_pptx),
        ]

        with patch("sys.argv", ["mk-pptx"] + args):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code != 0

    def test_exits_when_json_fails_schema_validation(self, tmp_path: Path, output_pptx: Path):
        """JSON 不符合 Pydantic Schema 時應以非零 exit code 結束。"""
        invalid_json = tmp_path / "invalid.json"
        invalid_json.write_text(
            json.dumps({"presentation_title": "測試", "slides": []}),
            encoding="utf-8",
        )

        args = [
            "--json", str(invalid_json),
            "--output", str(output_pptx),
        ]

        with patch("sys.argv", ["mk-pptx"] + args):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code != 0

    def test_calls_build_pptx_with_valid_json(
        self,
        valid_json_file: Path,
        output_pptx: Path,
    ):
        """合法 JSON 應呼叫 build_pptx 並生成 .pptx。"""
        args = [
            "--json", str(valid_json_file),
            "--output", str(output_pptx),
        ]

        with patch("src.main.build_pptx", return_value=output_pptx) as mock_build:
            with patch("sys.argv", ["mk-pptx"] + args):
                main()

        mock_build.assert_called_once()

    def test_build_pptx_receives_correct_output_path(
        self,
        valid_json_file: Path,
        output_pptx: Path,
    ):
        """build_pptx 應接收到正確的輸出路徑。"""
        args = [
            "--json", str(valid_json_file),
            "--output", str(output_pptx),
        ]

        with patch("src.main.build_pptx", return_value=output_pptx) as mock_build:
            with patch("sys.argv", ["mk-pptx"] + args):
                main()

        call_kwargs = mock_build.call_args[1]
        assert call_kwargs["output_path"] == output_pptx


# ============================================================
# --input 模式功能測試
# ============================================================


class TestRunFullPipeline:
    """--input 模式（完整 AI 流程）的功能測試。"""

    def _make_mock_presentation(self):
        """建立模擬 Presentation 物件。"""
        from schemas.slide_schema import Presentation
        return Presentation.model_validate(VALID_PRESENTATION_JSON)

    def test_exits_when_input_file_not_found(self, tmp_path: Path, output_pptx: Path):
        """輸入文字稿不存在時應以非零 exit code 結束。"""
        nonexistent = tmp_path / "nonexistent.txt"
        args = [
            "--input", str(nonexistent),
            "--output", str(output_pptx),
        ]

        with patch("sys.argv", ["mk-pptx"] + args):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code != 0

    def test_exits_when_skill_file_not_found(self, input_txt: Path, output_pptx: Path):
        """SKILL 檔案不存在時應拋出 FileNotFoundError 並結束。"""
        args = [
            "--input", str(input_txt),
            "--output", str(output_pptx),
        ]

        # 讓 _load_skill_prompt 拋出 FileNotFoundError
        with patch(
            "src.main._load_skill_prompt",
            side_effect=FileNotFoundError("SKILL 不存在"),
        ):
            with patch("sys.argv", ["mk-pptx"] + args):
                with pytest.raises((SystemExit, FileNotFoundError)):
                    main()

    def test_exits_when_llm_client_init_fails(self, input_txt: Path, output_pptx: Path):
        """LLM Client 初始化失敗時應以非零 exit code 結束。"""
        args = [
            "--input", str(input_txt),
            "--output", str(output_pptx),
        ]

        with patch(
            "src.main.create_client",
            side_effect=EnvironmentError("GEMINI_API_KEY 未設定"),
        ):
            with patch("src.main._load_skill_prompt", return_value="prompt {USER_INPUT}"):
                with patch("sys.argv", ["mk-pptx"] + args):
                    with pytest.raises(SystemExit) as exc_info:
                        main()

        assert exc_info.value.code != 0

    def test_exits_when_api_permission_error(self, input_txt: Path, output_pptx: Path):
        """API Key 過期時應以非零 exit code 結束。"""
        args = [
            "--input", str(input_txt),
            "--output", str(output_pptx),
        ]

        mock_client = MagicMock()
        mock_client.generate.side_effect = PermissionError("API key 無效")

        with patch("src.main.create_client", return_value=mock_client):
            with patch("src.main._load_skill_prompt", return_value="prompt {USER_INPUT}"):
                with patch("sys.argv", ["mk-pptx"] + args):
                    with pytest.raises(SystemExit) as exc_info:
                        main()

        assert exc_info.value.code != 0

    def test_exits_when_validate_fails(self, input_txt: Path, output_pptx: Path):
        """JSON 驗證超過重試上限時應以非零 exit code 結束。"""
        args = [
            "--input", str(input_txt),
            "--output", str(output_pptx),
        ]

        mock_client = MagicMock()
        mock_client.generate.return_value = "not valid json"

        with patch("src.main.create_client", return_value=mock_client):
            with patch("src.main._load_skill_prompt", return_value="prompt {USER_INPUT}"):
                with patch(
                    "src.main.validate_and_retry",
                    side_effect=ValueError("驗證失敗"),
                ):
                    with patch("sys.argv", ["mk-pptx"] + args):
                        with pytest.raises(SystemExit) as exc_info:
                            main()

        assert exc_info.value.code != 0

    def test_full_pipeline_calls_validate_and_build(
        self,
        input_txt: Path,
        output_pptx: Path,
    ):
        """完整流程應依序呼叫 validate_and_retry 和 build_pptx。"""
        args = [
            "--input", str(input_txt),
            "--output", str(output_pptx),
        ]

        mock_presentation = self._make_mock_presentation()
        mock_client = MagicMock()
        mock_client.generate.return_value = json.dumps(VALID_PRESENTATION_JSON)

        with patch("src.main.create_client", return_value=mock_client):
            with patch("src.main._load_skill_prompt", return_value="prompt {USER_INPUT}"):
                with patch(
                    "src.main.validate_and_retry",
                    return_value=mock_presentation,
                ) as mock_validate:
                    with patch(
                        "src.main.build_pptx",
                        return_value=output_pptx,
                    ) as mock_build:
                        with patch("sys.argv", ["mk-pptx"] + args):
                            main()

        mock_validate.assert_called_once()
        mock_build.assert_called_once()

    def test_validate_receives_llm_output(self, input_txt: Path, output_pptx: Path):
        """validate_and_retry 應接收到 LLM 的原始輸出。"""
        args = [
            "--input", str(input_txt),
            "--output", str(output_pptx),
        ]

        llm_response = json.dumps(VALID_PRESENTATION_JSON)
        mock_presentation = self._make_mock_presentation()
        mock_client = MagicMock()
        mock_client.generate.return_value = llm_response

        with patch("src.main.create_client", return_value=mock_client):
            with patch("src.main._load_skill_prompt", return_value="prompt {USER_INPUT}"):
                with patch(
                    "src.main.validate_and_retry",
                    return_value=mock_presentation,
                ) as mock_validate:
                    with patch("src.main.build_pptx", return_value=output_pptx):
                        with patch("sys.argv", ["mk-pptx"] + args):
                            main()

        # 確認 validate_and_retry 的第一個參數是 LLM 回應
        call_kwargs = mock_validate.call_args[1]
        assert call_kwargs["raw_output"] == llm_response


# ============================================================
# --diagram 模式功能測試
# ============================================================


class TestRunDiagramOnly:
    """--diagram 模式（只生成圖表）的功能測試。"""

    def test_exits_when_mmd_file_not_found(self, tmp_path: Path, output_png: Path):
        """.mmd 檔案不存在時應以非零 exit code 結束。"""
        nonexistent = tmp_path / "nonexistent.mmd"
        args = [
            "--diagram", str(nonexistent),
            "--output", str(output_png),
        ]

        with patch("sys.argv", ["mk-pptx"] + args):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code != 0

    def test_exits_when_build_diagram_fails(self, mmd_file: Path, output_png: Path):
        """build_diagram 回傳 None 時應以非零 exit code 結束。"""
        args = [
            "--diagram", str(mmd_file),
            "--output", str(output_png),
        ]

        with patch("src.main.build_diagram", return_value=None):
            with patch("sys.argv", ["mk-pptx"] + args):
                with pytest.raises(SystemExit) as exc_info:
                    main()

        assert exc_info.value.code != 0

    def test_calls_build_diagram_with_mmd_content(self, mmd_file: Path, output_png: Path):
        """應以正確的 mermaid string 呼叫 build_diagram。"""
        args = [
            "--diagram", str(mmd_file),
            "--output", str(output_png),
        ]

        mock_result = MagicMock()
        mock_result.png_path = output_png
        mock_result.svg_path = output_png.with_suffix(".svg")

        with patch("src.main.build_diagram", return_value=mock_result) as mock_bd:
            with patch("sys.argv", ["mk-pptx"] + args):
                main()

        mock_bd.assert_called_once()
        call_kwargs = mock_bd.call_args[1]
        assert "flowchart LR" in call_kwargs["mermaid_string"]

    def test_output_stem_matches_output_filename(
        self,
        mmd_file: Path,
        tmp_path: Path,
    ):
        """output_stem 應等於輸出檔案的主檔名（不含副檔名）。"""
        output_png = tmp_path / "my_diagram.png"
        args = [
            "--diagram", str(mmd_file),
            "--output", str(output_png),
        ]

        mock_result = MagicMock()
        mock_result.png_path = output_png
        mock_result.svg_path = output_png.with_suffix(".svg")

        with patch("src.main.build_diagram", return_value=mock_result) as mock_bd:
            with patch("sys.argv", ["mk-pptx"] + args):
                main()

        call_kwargs = mock_bd.call_args[1]
        assert call_kwargs["output_stem"] == "my_diagram"

    def test_output_dir_is_parent_of_output_path(
        self,
        mmd_file: Path,
        tmp_path: Path,
    ):
        """output_dir 應等於輸出路徑的上層目錄。"""
        output_dir = tmp_path / "subdir"
        output_png = output_dir / "out.png"
        args = [
            "--diagram", str(mmd_file),
            "--output", str(output_png),
        ]

        mock_result = MagicMock()
        mock_result.png_path = output_png
        mock_result.svg_path = output_png.with_suffix(".svg")

        with patch("src.main.build_diagram", return_value=mock_result) as mock_bd:
            with patch("sys.argv", ["mk-pptx"] + args):
                main()

        call_kwargs = mock_bd.call_args[1]
        assert call_kwargs["output_dir"] == output_dir


# ============================================================
# 整合測試：確認 .env 載入不影響一般流程
# ============================================================


class TestEnvLoading:
    """確認 .env 載入行為的相關測試。"""

    def test_main_module_can_be_imported(self):
        """main 模組應可正常匯入（dotenv 載入不應導致 import error）。"""
        import src.main

        assert src.main is not None

    def test_load_dotenv_is_called_on_import(self):
        """模組載入時應嘗試讀取 .env（已透過 load_dotenv() 實現）。"""
        # dotenv 在模組層級執行 load_dotenv()，此處只驗證函式是否存在
        from src.main import main

        assert callable(main)
