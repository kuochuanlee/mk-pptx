"""
build_diagram.py 測試。

測試策略：
  - 所有需要實際 mmdc 的測試：用 pytest.mark.mmdc 標記，
    在 mmdc 不可用時自動 skip（符合計畫 10-4 CI 注意事項）
  - mmdc 失敗的 fallback 行為：用 unittest.mock patch subprocess.run，
    不依賴真實 mmdc 環境
  - 暫存檔寫入邏輯：純 Python 邏輯，無需 mmdc

測試範圍：
  - _write_temp_mmd()：換行還原、檔案內容正確
  - is_mmdc_available()：可用性偵測
  - build_diagram()：mmdc 失敗時回傳 None（mock）
  - build_diagram()：各種 mermaid 圖表類型的渲染（需 mmdc，自動 skip）
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.build_diagram import (
    DiagramResult,
    _write_temp_mmd,
    build_diagram,
    is_mmdc_available,
)

# ============================================================
# pytest mark：需要 mmdc 的測試自動 skip
# ============================================================

# 在模組載入時就判斷，避免每個測試重複呼叫
_MMDC_AVAILABLE = is_mmdc_available()

requires_mmdc = pytest.mark.skipif(
    not _MMDC_AVAILABLE,
    reason="mmdc 未安裝，跳過此測試（符合計畫 10-4 CI 注意事項）",
)


# ============================================================
# _write_temp_mmd() 測試（純 Python 邏輯，無需 mmdc）
# ============================================================


class TestWriteTempMmd:
    """暫存 .mmd 檔寫入邏輯測試。"""

    def test_creates_file_with_mmd_suffix(self):
        """建立的暫存檔應有 .mmd 副檔名。"""
        tmp = _write_temp_mmd("flowchart LR\n  A --> B")

        try:
            assert tmp.suffix == ".mmd"
            assert tmp.exists()
        finally:
            tmp.unlink(missing_ok=True)

    def test_file_content_is_correct(self):
        """寫入的內容應為正確的 mermaid 語法。"""
        mermaid = "flowchart LR\n  A[開始] --> B[結束]"
        tmp = _write_temp_mmd(mermaid)

        try:
            content = tmp.read_text(encoding="utf-8")
            assert "flowchart LR" in content
            assert "A[開始]" in content
        finally:
            tmp.unlink(missing_ok=True)

    def test_literal_newline_escape_is_restored(self):
        """字面上的 \\n 應還原為真正的換行。"""
        # JSON 中通常以字面 \n 儲存
        mermaid_with_literal_newline = "flowchart LR\\n  A --> B\\n  B --> C"
        tmp = _write_temp_mmd(mermaid_with_literal_newline)

        try:
            content = tmp.read_text(encoding="utf-8")
            # 還原後應包含真正的換行
            assert "\n" in content
            assert "\\n" not in content
        finally:
            tmp.unlink(missing_ok=True)

    def test_real_newline_preserved(self):
        """已是真正換行的字串不應被重複處理。"""
        mermaid = "flowchart LR\n  A --> B"
        tmp = _write_temp_mmd(mermaid)

        try:
            content = tmp.read_text(encoding="utf-8")
            lines = content.splitlines()
            assert lines[0] == "flowchart LR"
            assert "A --> B" in lines[1]
        finally:
            tmp.unlink(missing_ok=True)

    def test_chinese_content_is_preserved(self):
        """中文內容應以 UTF-8 正確寫入。"""
        mermaid = "flowchart LR\n  A[開始] --> B[資料驗證] --> C{通過?}"
        tmp = _write_temp_mmd(mermaid)

        try:
            content = tmp.read_text(encoding="utf-8")
            assert "開始" in content
            assert "資料驗證" in content
            assert "通過?" in content
        finally:
            tmp.unlink(missing_ok=True)


# ============================================================
# is_mmdc_available() 測試
# ============================================================


class TestIsMmdcAvailable:
    """mmdc 可用性偵測測試。"""

    def test_returns_bool(self):
        """is_mmdc_available() 應回傳 bool。"""
        result = is_mmdc_available()

        assert isinstance(result, bool)

    def test_with_valid_mmdc_path_env(self, tmp_path: Path):
        """MMDC_PATH 指向存在的可執行檔時，應回傳 True。"""
        # 建立一個假的可執行檔
        fake_mmdc = tmp_path / "mmdc.exe"
        fake_mmdc.write_text("fake")

        with patch.dict("os.environ", {"MMDC_PATH": str(fake_mmdc)}):
            result = is_mmdc_available()

        assert result is True

    def test_with_invalid_mmdc_path_env(self, tmp_path: Path):
        """MMDC_PATH 指向不存在路徑時，應 fallback 至 PATH 搜尋。"""
        fake_path = str(tmp_path / "nonexistent_mmdc.exe")

        with patch.dict("os.environ", {"MMDC_PATH": fake_path}):
            # 再 patch shutil.which 讓 PATH 也找不到
            with patch("shutil.which", return_value=None):
                result = is_mmdc_available()

        assert result is False


# ============================================================
# build_diagram() 失敗行為測試（mock subprocess，不需要真實 mmdc）
# ============================================================


class TestBuildDiagramFailure:
    """build_diagram() 失敗情境測試，使用 mock 不依賴真實 mmdc。"""

    def test_returns_none_when_mmdc_not_found(self, tmp_path: Path):
        """找不到 mmdc 時應回傳 None（不拋例外）。"""
        with patch("src.build_diagram._find_mmdc", return_value=None):
            result = build_diagram(
                mermaid_string="flowchart LR\n  A --> B",
                output_stem="test",
                output_dir=tmp_path,
            )

        assert result is None

    def test_returns_none_when_mmdc_exit_nonzero(self, tmp_path: Path):
        """mmdc 執行失敗（exit code != 0）時應回傳 None。"""
        # mock _find_mmdc 讓程式認為 mmdc 存在
        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            # mock subprocess.run 讓其模擬失敗
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "Parse error in mermaid syntax"

            with patch("subprocess.run", return_value=mock_result):
                result = build_diagram(
                    mermaid_string="flowchart LR\n  A --> B",
                    output_stem="test",
                    output_dir=tmp_path,
                )

        assert result is None

    def test_returns_none_when_mmdc_timeout(self, tmp_path: Path):
        """mmdc 執行逾時時應回傳 None（不拋例外）。"""
        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            with patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="mmdc", timeout=60),
            ):
                result = build_diagram(
                    mermaid_string="flowchart LR\n  A --> B",
                    output_stem="test",
                    output_dir=tmp_path,
                )

        assert result is None

    def test_temp_file_cleaned_up_on_failure(self, tmp_path: Path):
        """mmdc 失敗時，暫存 .mmd 檔應被清理。"""
        # 記錄建立的暫存檔路徑
        created_tmp_paths: list[Path] = []

        original_write_temp_mmd = _write_temp_mmd

        def tracking_write_temp_mmd(mermaid_string: str) -> Path:
            path = original_write_temp_mmd(mermaid_string)
            created_tmp_paths.append(path)
            return path

        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "Error"

            with patch("subprocess.run", return_value=mock_result):
                with patch(
                    "src.build_diagram._write_temp_mmd",
                    side_effect=tracking_write_temp_mmd,
                ):
                    build_diagram(
                        mermaid_string="flowchart LR\n  A --> B",
                        output_stem="test",
                        output_dir=tmp_path,
                    )

        # 所有暫存檔應已被清理
        for tmp_path_item in created_tmp_paths:
            assert not tmp_path_item.exists(), f"暫存檔未清理：{tmp_path_item}"

    def test_output_dir_created_if_not_exists(self, tmp_path: Path):
        """output_dir 不存在時應自動建立。"""
        new_dir = tmp_path / "nested" / "output"

        assert not new_dir.exists()

        with patch("src.build_diagram._find_mmdc", return_value=None):
            build_diagram(
                mermaid_string="flowchart LR\n  A --> B",
                output_stem="test",
                output_dir=new_dir,
            )

        # 即使 mmdc 找不到，目錄仍應在嘗試後存在
        # 注意：_find_mmdc 回傳 None 時，程式在 mkdir 之前就 return None
        # 所以此處目錄不一定存在，這是符合預期的行為
        # 改為測試 mmdc 存在但失敗的情況
        new_dir2 = tmp_path / "nested2" / "output"

        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_result.stderr = "Error"

            with patch("subprocess.run", return_value=mock_result):
                build_diagram(
                    mermaid_string="flowchart LR\n  A --> B",
                    output_stem="test",
                    output_dir=new_dir2,
                )

        assert new_dir2.exists()

    def test_returns_none_does_not_raise(self, tmp_path: Path):
        """mmdc 失敗時不應拋出例外，僅回傳 None。"""
        with patch("src.build_diagram._find_mmdc", return_value=None):
            # 不應拋出任何例外
            result = build_diagram(
                mermaid_string="flowchart LR\n  A --> B",
                output_stem="test",
                output_dir=tmp_path,
            )

        assert result is None


# ============================================================
# build_diagram() 成功行為測試（mock subprocess 模擬成功）
# ============================================================


class TestBuildDiagramSuccess:
    """build_diagram() 成功情境測試，mock subprocess 讓其模擬成功。"""

    def _make_subprocess_side_effect(self) -> MagicMock:
        """建立模擬成功的 subprocess.run side_effect。

        build_diagram.py 在 subprocess 成功後會檢查 output_path.exists()，
        因此 side_effect 需要在被呼叫時根據 -o 參數建立對應的假輸出檔案。
        """

        def _fake_run(cmd, **kwargs):
            # 從指令中解析 -o 參數後面的輸出路徑
            try:
                o_idx = cmd.index("-o")
                out_path = Path(cmd[o_idx + 1])
                out_path.touch()
            except (ValueError, IndexError):
                pass

            # 回傳模擬成功的結果
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            return mock_result

        return _fake_run

    def test_returns_diagram_result_on_success(self, tmp_path: Path):
        """mmdc 成功時應回傳 DiagramResult 物件。"""
        fake_run = self._make_subprocess_side_effect()

        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            with patch("subprocess.run", side_effect=fake_run):
                result = build_diagram(
                    mermaid_string="flowchart LR\n  A --> B",
                    output_stem="slide_3",
                    output_dir=tmp_path,
                )

        assert result is not None
        assert isinstance(result, DiagramResult)

    def test_png_path_has_correct_name(self, tmp_path: Path):
        """回傳的 png_path 應有正確的主檔名和副檔名。"""
        fake_run = self._make_subprocess_side_effect()

        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            with patch("subprocess.run", side_effect=fake_run):
                result = build_diagram(
                    mermaid_string="flowchart LR\n  A --> B",
                    output_stem="slide_3_diagram",
                    output_dir=tmp_path,
                )

        assert result is not None
        assert result.png_path.name == "slide_3_diagram.png"
        assert result.png_path.suffix == ".png"

    def test_svg_path_has_correct_name(self, tmp_path: Path):
        """回傳的 svg_path 應有正確的主檔名和副檔名。"""
        fake_run = self._make_subprocess_side_effect()

        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            with patch("subprocess.run", side_effect=fake_run):
                result = build_diagram(
                    mermaid_string="flowchart LR\n  A --> B",
                    output_stem="slide_3_diagram",
                    output_dir=tmp_path,
                )

        assert result is not None
        assert result.svg_path.name == "slide_3_diagram.svg"
        assert result.svg_path.suffix == ".svg"

    def test_subprocess_called_twice(self, tmp_path: Path):
        """應呼叫 subprocess.run 兩次（PNG 和 SVG 各一次）。"""
        fake_run = self._make_subprocess_side_effect()

        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            with patch("subprocess.run", side_effect=fake_run) as mock_run:
                build_diagram(
                    mermaid_string="flowchart LR\n  A --> B",
                    output_stem="test",
                    output_dir=tmp_path,
                )

        assert mock_run.call_count == 2

    def test_png_command_includes_scale_flag(self, tmp_path: Path):
        """PNG 渲染指令應包含 -s 縮放參數。"""
        fake_run = self._make_subprocess_side_effect()

        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            with patch("subprocess.run", side_effect=fake_run) as mock_run:
                build_diagram(
                    mermaid_string="flowchart LR\n  A --> B",
                    output_stem="test",
                    output_dir=tmp_path,
                )

        # 第一次呼叫（PNG）的指令應包含 -s
        first_call_args = mock_run.call_args_list[0][0][0]
        assert "-s" in first_call_args

    def test_svg_command_excludes_scale_flag(self, tmp_path: Path):
        """SVG 渲染指令不應包含 -s 縮放參數。"""
        fake_run = self._make_subprocess_side_effect()

        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            with patch("subprocess.run", side_effect=fake_run) as mock_run:
                build_diagram(
                    mermaid_string="flowchart LR\n  A --> B",
                    output_stem="test",
                    output_dir=tmp_path,
                )

        # 第二次呼叫（SVG）的指令不應包含 -s
        second_call_args = mock_run.call_args_list[1][0][0]
        assert "-s" not in second_call_args

    def test_config_included_when_exists(self, tmp_path: Path):
        """mmdc 設定檔存在時，指令應包含 -c 參數。"""
        fake_run = self._make_subprocess_side_effect()

        # 建立假的設定檔
        config_file = tmp_path / "mermaid.json"
        config_file.write_text("{}")

        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            with patch("subprocess.run", side_effect=fake_run) as mock_run:
                build_diagram(
                    mermaid_string="flowchart LR\n  A --> B",
                    output_stem="test",
                    output_dir=tmp_path,
                    config_path=config_file,
                )

        # 兩次呼叫都應包含 -c
        for call in mock_run.call_args_list:
            args = call[0][0]
            assert "-c" in args

    def test_config_excluded_when_not_exists(self, tmp_path: Path):
        """mmdc 設定檔不存在時，指令不應包含 -c 參數。"""
        fake_run = self._make_subprocess_side_effect()

        nonexistent_config = tmp_path / "nonexistent.json"

        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            with patch("subprocess.run", side_effect=fake_run) as mock_run:
                build_diagram(
                    mermaid_string="flowchart LR\n  A --> B",
                    output_stem="test",
                    output_dir=tmp_path,
                    config_path=nonexistent_config,
                )

        # 兩次呼叫都不應包含 -c
        for call in mock_run.call_args_list:
            args = call[0][0]
            assert "-c" not in args

    def test_temp_file_cleaned_up_on_success(self, tmp_path: Path):
        """mmdc 成功時，暫存 .mmd 檔也應被清理。"""
        created_tmp_paths: list[Path] = []

        original_write_temp_mmd = _write_temp_mmd

        def tracking_write_temp_mmd(mermaid_string: str) -> Path:
            path = original_write_temp_mmd(mermaid_string)
            created_tmp_paths.append(path)
            return path

        fake_run = self._make_subprocess_side_effect()

        with patch("src.build_diagram._find_mmdc", return_value=["/fake/mmdc"]):
            with patch("subprocess.run", side_effect=fake_run):
                with patch(
                    "src.build_diagram._write_temp_mmd",
                    side_effect=tracking_write_temp_mmd,
                ):
                    build_diagram(
                        mermaid_string="flowchart LR\n  A --> B",
                        output_stem="test",
                        output_dir=tmp_path,
                    )

        # 成功後暫存檔也應已被清理
        for tmp_path_item in created_tmp_paths:
            assert not tmp_path_item.exists(), f"暫存檔未清理：{tmp_path_item}"


# ============================================================
# 真實 mmdc 整合測試（自動 skip 若 mmdc 未安裝）
# ============================================================


class TestBuildDiagramIntegration:
    """使用真實 mmdc 的整合測試，mmdc 未安裝時自動 skip。"""

    @requires_mmdc
    def test_flowchart_renders_png(self, tmp_path: Path):
        """flowchart 類型應能成功渲染 PNG。"""
        result = build_diagram(
            mermaid_string="flowchart LR\n  A[開始] --> B[結束]",
            output_stem="test_flowchart",
            output_dir=tmp_path,
        )

        assert result is not None
        assert result.png_path.exists()

    @requires_mmdc
    def test_flowchart_renders_svg(self, tmp_path: Path):
        """flowchart 類型應能成功渲染 SVG。"""
        result = build_diagram(
            mermaid_string="flowchart LR\n  A[開始] --> B[結束]",
            output_stem="test_flowchart",
            output_dir=tmp_path,
        )

        assert result is not None
        assert result.svg_path.exists()

    @requires_mmdc
    def test_sequence_diagram_renders(self, tmp_path: Path):
        """sequenceDiagram 類型應能成功渲染。"""
        result = build_diagram(
            mermaid_string="sequenceDiagram\n  A->>B: 呼叫\n  B-->>A: 回應",
            output_stem="test_sequence",
            output_dir=tmp_path,
        )

        assert result is not None
        assert result.png_path.exists()

    @requires_mmdc
    def test_state_diagram_renders(self, tmp_path: Path):
        """stateDiagram-v2 類型應能成功渲染。"""
        result = build_diagram(
            mermaid_string="stateDiagram-v2\n  [*] --> 待審\n  待審 --> 通過\n  待審 --> 拒絕",
            output_stem="test_state",
            output_dir=tmp_path,
        )

        assert result is not None
        assert result.png_path.exists()

    @requires_mmdc
    def test_er_diagram_renders(self, tmp_path: Path):
        """erDiagram 類型應能成功渲染。"""
        result = build_diagram(
            mermaid_string="erDiagram\n  USER ||--o{ ORDER : places",
            output_stem="test_er",
            output_dir=tmp_path,
        )

        assert result is not None
        assert result.png_path.exists()

    @requires_mmdc
    def test_with_mermaid_config(self, tmp_path: Path):
        """使用 config/mermaid.json 設定檔應能正常渲染。"""
        config_path = Path("config") / "mermaid.json"

        result = build_diagram(
            mermaid_string="flowchart LR\n  A[開始] --> B[結束]",
            output_stem="test_with_config",
            output_dir=tmp_path,
            config_path=config_path,
        )

        assert result is not None
        assert result.png_path.exists()
