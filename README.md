# mk-pptx

AI 輔助企業簡報自動化工具。輸入業務文字稿，透過 LLM 自動結構化為投影片 JSON，經 Pydantic 驗證後，由 python-pptx 組裝成 .pptx 檔案。可選搭配 Mermaid CLI (mmdc) 自動渲染流程圖。

## 架構概覽

```
文字稿 -> LLM (json_outline SKILL) -> JSON -> Pydantic 驗證 -> python-pptx -> .pptx
                                                                     |
草圖描述 -> LLM (mermaid_diagram SKILL) -> Mermaid -> mmdc -> .png / .svg -+
```

AI 只負責結構化輸出，版面配置全部由程式掌控，確保輸出一致性。

## 功能特點

- **三種操作模式**：完整 AI 流程、從既有 JSON 建立、單獨渲染圖表
- **7 種投影片版面**：封面、章節分隔、條列、表格、條列+表格、圖表、條列+圖表
- **自動 retry**：LLM 輸出格式錯誤時最多重試 3 次，附上錯誤訊息引導 LLM 修正
- **多 LLM 支援**：透過環境變數切換 Google Gemini（家用）或 Azure OpenAI（公司）
- **圖表 fallback**：mmdc 渲染失敗時自動降級為文字，不中斷整份簡報生成
- **Pydantic Schema 驗證**：含跨 slide 重複編號偵測、條件欄位一致性檢查

## 目錄結構

```
mk-pptx/
├── config/
│   ├── mermaid.json          # mmdc 色彩與字型設定
│   ├── template_map.json     # 模板 placeholder 對應設定
│   └── .gitkeep              # (template.pptx 不納入版控)
├── docs/
│   └── pptx_automation_plan.md  # 完整實作計畫文件
├── input/                    # 放置輸入素材（文字稿、.mmd 檔）
├── output/                   # 產出檔案（.pptx、.png、.svg）
├── schemas/
│   └── slide_schema.py       # Pydantic 資料模型定義
├── skills/
│   ├── json_outline.md       # SKILL: 文字稿 -> 簡報 JSON
│   └── mermaid_diagram.md    # SKILL: 草圖描述 -> Mermaid 語法
├── src/
│   ├── main.py               # CLI 統一入口
│   ├── llm_client.py         # LLM 呼叫抽象層（Gemini / Azure OpenAI）
│   ├── validate.py           # JSON 驗證與 auto-retry
│   ├── build_pptx.py         # JSON -> .pptx 核心邏輯
│   ├── build_diagram.py      # Mermaid -> PNG / SVG
│   └── table_parser.py       # Markdown 表格解析（純 Python）
├── template/                 # 公司 .pptx 模板（不納入版控）
├── tests/                    # pytest 測試套件
├── .env.example              # 環境變數範本
├── pyproject.toml
└── uv.lock
```

## 環境需求

| 工具 | 版本 | 用途 |
|---|---|---|
| Python | >= 3.13 | 主要執行環境 |
| uv | 任意 | 虛擬環境與套件管理 |
| Node.js + npm | >= 18 | 驅動 mmdc（圖表渲染，可選） |

## 安裝

### 1. 建立虛擬環境

```bash
uv venv --python "C:\Users\<你的帳號>\AppData\Local\Programs\Python\Python313\python.exe"
```

### 2. 安裝核心依賴

```bash
# 僅使用 Gemini
uv pip install -e ".[gemini,dev]"

# 僅使用 Azure OpenAI
uv pip install -e ".[azure,dev]"

# 同時安裝兩者
uv pip install -e ".[all,dev]"
```

> `[gemini]` 內部使用新版 `google-genai` SDK，已取代已棄用的 `google-generativeai`。

### 3. 安裝 Mermaid CLI（圖表渲染，可選）

```bash
npm install
```

> 若不安裝，含 `mermaid` 的 slide 會自動 fallback 為文字顯示，不影響其他版面的生成。

### 4. 設定環境變數

複製 `.env.example` 為 `.env` 並填入 API key：

```bash
cp .env.example .env
```

```dotenv
# 選擇 backend：gemini 或 azure_openai
LLM_BACKEND=gemini

# Google Gemini（家用）
GEMINI_API_KEY=your-gemini-api-key-here

# Azure OpenAI（公司，key 每 7 天過期）
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=your-azure-openai-key-here
AZURE_OPENAI_DEPLOYMENT=gpt-4o
```

### 5. 放置模板檔案

將公司 .pptx 模板放至 `template/` 目錄，並確認 `config/template_map.json` 中的路徑與 placeholder index 設定正確。

> 使用 `scan_template.py` 可列印模板中所有 layout 名稱與 placeholder index，協助填寫 `template_map.json`：
> ```bash
> uv run python scan_template.py
> ```

## 使用方式

### 完整流程：文字稿 -> AI -> PPTX

```bash
python -m src.main --input input/briefing.txt --output output/report.pptx
```

執行步驟：
1. 讀取文字稿
2. 呼叫 LLM 使用 `json_outline` SKILL 生成 JSON
3. Pydantic 驗證（失敗自動 retry 最多 3 次）
4. python-pptx 組裝 .pptx

### 從既有 JSON 生成 PPTX（跳過 AI）

```bash
python -m src.main --json input/slides.json --output output/report.pptx
```

適合手動調整 JSON 後重新生成，或在不需要 LLM 的環境中執行。

### 只渲染 Mermaid 圖表

```bash
python -m src.main --diagram input/flow.mmd --output output/flow.png
```

同時輸出 `.png`（供 PPTX 插圖）和 `.svg`（母檔，供手動微調）。

### 選項說明

```
--input FILE         輸入文字稿路徑
--json FILE          輸入 JSON 檔案路徑（跳過 AI）
--diagram FILE       輸入 .mmd 檔路徑（只生成圖表）
--output, -o FILE    輸出路徑（.pptx 或 .png）
--template-map FILE  template_map.json 路徑（預設：config/template_map.json）
--verbose, -v        啟用 DEBUG 等級 log
```

## 投影片版面類型

JSON 中每頁 slide 以 `layout_type` 指定版面，對應如下：

| layout_type | content 必要欄位 | 說明 |
|---|---|---|
| `title_slide` | `subtitle`（可選） | 封面頁 |
| `section_divider` | `subtitle`（可選） | 章節分隔頁 |
| `bullets_only` | `bullets` | 純條列重點頁 |
| `table_only` | `markdown_table` | 純表格頁 |
| `bullets_with_table` | `bullets` + `markdown_table` | 條列＋表格（左右分欄） |
| `diagram_only` | `mermaid` | 純流程圖頁（mmdc 渲染） |
| `bullets_with_diagram` | `bullets` + `mermaid` | 條列＋流程圖（左右分欄） |

## JSON 結構範例

```json
{
  "presentation_title": "Q2 營運報告",
  "author": "王小明",
  "date": "2025-06-01",
  "slides": [
    {
      "slide_number": 1,
      "layout_type": "title_slide",
      "title": "Q2 營運報告",
      "speaker_notes": "今天向各位長官報告第二季的整體成效。",
      "content": {
        "subtitle": "2025 年第二季"
      }
    },
    {
      "slide_number": 2,
      "layout_type": "bullets_with_table",
      "title": "Q2 核心指標",
      "speaker_notes": "三個區域均達標，成本下降主要來自物流優化。",
      "content": {
        "bullets": [
          "整體成長 15%",
          "三個區域均達標",
          "成本下降 7%"
        ],
        "markdown_table": "| 指標 | Q1 | Q2 |\n|---|---|---|\n| 營收 | 100 | 115 |\n| 成本 | 80 | 74 |"
      }
    }
  ]
}
```

## 設定檔

### config/template_map.json

定義 .pptx 模板路徑與各 `layout_type` 對應的 slide layout 名稱及 placeholder index：

```json
{
  "template_path": "template/your-template.pptx",
  "slide_width_emu": 9144000,
  "slide_height_emu": 5143500,
  "layouts": {
    "title_slide": {
      "layout_name": "Cover Slide layout",
      "title_idx": 10,
      "subtitle_idx": 11
    }
  }
}
```

### config/mermaid.json

mmdc 的主題色彩與字型設定，可依公司視覺規範調整：

```json
{
  "theme": "base",
  "themeVariables": {
    "primaryColor": "#005BAC",
    "primaryTextColor": "#FFFFFF",
    "fontFamily": "Noto Sans TC, Microsoft JhengHei, sans-serif",
    "fontSize": "16px"
  }
}
```

## 開發

### 執行測試

```bash
# 執行所有測試
python -m pytest tests/ -v

# 只執行單一模組
python -m pytest tests/test_schema.py -v

# 含 debug log
python -m pytest tests/ -v -s
```

### 測試覆蓋範圍

| 測試檔案 | 覆蓋模組 | 說明 |
|---|---|---|
| `test_schema.py` | `slide_schema.py` | Schema 驗證、條件欄位、跨 slide 檢查 |
| `test_table_parser.py` | `table_parser.py` | Markdown 表格解析、邊界條件 |
| `test_build_pptx.py` | `build_pptx.py` | 每種 layout 的 PPTX 生成（需模板） |
| `test_build_diagram.py` | `build_diagram.py` | mmdc 渲染（需 mmdc）、失敗 fallback（mock） |
| `test_validate.py` | `validate.py` | JSON 解析、Pydantic 驗證、retry 邏輯 |
| `test_main.py` | `main.py` | CLI 三種模式、argument parser、錯誤處理 |

> `test_build_pptx.py` 依賴 `template/` 下的模板，不存在時自動 skip。
> `test_build_diagram.py` 中的整合測試依賴 mmdc，未安裝時自動 skip。

### 依賴安全掃描

```bash
uv run pip-audit
```

## LLM 切換

透過 `.env` 中的 `LLM_BACKEND` 環境變數切換，無需修改程式碼：

| 環境值 | 對應實作 | 必要環境變數 |
|---|---|---|
| `gemini`（預設） | Google Gemini API | `GEMINI_API_KEY` |
| `azure_openai` | Azure OpenAI | `AZURE_OPENAI_ENDPOINT`、`AZURE_OPENAI_KEY` |

可選設定：
- `GEMINI_MODEL`：指定 Gemini 模型名稱（預設 `gemini-2.0-flash`）
- `AZURE_OPENAI_DEPLOYMENT`：指定部署名稱（預設 `gpt-4o`）

## 已知限制

| 限制 | 說明 |
|---|---|
| python-pptx 不支援 SVG 插入 | 圖表一律以 PNG 格式插入 PPTX |
| Mermaid 支援類型 | 僅支援 `flowchart`、`sequenceDiagram`、`classDiagram`、`stateDiagram-v2`、`erDiagram` |
| Azure API key 效期 | 公司環境 API key 每 7 天過期，需重新申請 |

## 版本控制規範

納入版控：

```
docs/       # 實作計畫文件
skills/     # Prompt 版本演進（git diff 追蹤調整歷史）
schemas/    # Schema 變更紀錄
config/     # mermaid.json（不含 template.pptx）
src/        # 程式邏輯
tests/      # 測試程式碼
pyproject.toml
```

排除版控（.gitignore）：

```
.env                 # 含 API key，禁止上傳
config/template.pptx # 公司機密模板
template/            # 公司機密模板
output/              # 產出檔案
.venv/               # 虛擬環境
__pycache__/
```
