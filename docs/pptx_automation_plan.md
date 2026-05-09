# 簡報自動化實作計畫

> 雙軌並行架構：文字->PPTX、草圖->SVG，AI 只負責結構化輸出，排版全程式化掌控

---

## 整體架構

```
文字內容 -> LLM Client -> AI (SKILL: json_outline) -> JSON -> validate (Pydantic) -> build_pptx (python-pptx) -> .pptx
                                                                                           |
手繪草圖 -> LLM Client -> AI (SKILL: mermaid_diagram) -> Mermaid -> 手動微調 -> build_diagram (mmdc) -> .png / .svg -+
```

---

## 專案目錄結構

```
mk-pptx/
├── docs/
│   └── pptx_automation_plan.md  # 本文件
├── skills/
│   ├── json_outline.md          # Prompt：文字內容 -> JSON
│   └── mermaid_diagram.md       # Prompt：草圖描述 -> Mermaid
├── schemas/
│   └── slide_schema.py          # Pydantic 資料模型定義
├── config/
│   ├── template.pptx            # 公司簡報模板（勿修改）
│   └── mermaid.json             # mmdc 樣式設定（色系、字型）
├── src/
│   ├── llm_client.py            # LLM 呼叫抽象層（支援多 backend 切換）
│   ├── validate.py              # JSON 驗證與 retry 邏輯
│   ├── build_pptx.py            # JSON -> .pptx 主邏輯
│   ├── build_diagram.py         # Mermaid -> .png / .svg
│   ├── table_parser.py          # 純 Python markdown table 解析器
│   └── main.py                  # CLI 統一入口
├── tests/
│   ├── test_schema.py           # Schema 驗證測試
│   ├── test_table_parser.py     # markdown table 解析測試
│   ├── test_build_pptx.py       # PPTX 生成整合測試
│   └── test_build_diagram.py    # Mermaid 渲染測試
├── input/                       # 放置輸入素材（文字稿、草圖描述）
├── output/                      # 產出檔案（.pptx、.png、.svg）
├── pyproject.toml               # 專案依賴與元資料
└── .gitignore
```

---

## 階段一：專案初始化（pyproject.toml）

### 1-1 pyproject.toml 定義

```toml
[project]
name = "mk-pptx"
version = "0.1.0"
description = "AI 輔助企業簡報自動化工具"
requires-python = ">=3.13"
dependencies = [
    "python-pptx==1.0.2",
    "pydantic>=2.0,<3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pip-audit",
]

[project.scripts]
mk-pptx = "src.main:main"
```

> python-pptx 鎖定版本 1.0.2，避免未來不可預期的破壞性變更。
> 該專案目前維護活動低，但功能穩定且無已知 CVE，定期用 `pip-audit` 掃描即可。

### 1-2 建立虛擬環境與安裝

```bash
# 建立虛擬環境
uv venv --python "C:\Users\kuoch\AppData\Local\Programs\Python\Python313\python.exe"

# 安裝依賴
uv pip install -e ".[dev]"
```

---

## 階段二：定義 Schema（schemas/slide_schema.py）

### 2-1 支援的 layout_type 列舉

| layout_type | content 包含欄位 | 說明 |
|---|---|---|
| `title_slide` | `subtitle` | 封面頁 |
| `section_divider` | `subtitle`（可選） | 章節分隔頁 |
| `bullets_only` | `bullets` | 純條列頁 |
| `table_only` | `markdown_table` | 純表格頁 |
| `bullets_with_table` | `bullets` + `markdown_table` | 條列+表格混合頁 |
| `diagram_only` | `mermaid` | 純流程圖頁 |
| `bullets_with_diagram` | `bullets` + `mermaid` | 條列+流程圖混合頁 |

### 2-2 頂層 JSON 結構

```json
{
  "presentation_title": "Q2 營運報告",
  "author": "王小明",
  "date": "2025-06-01",
  "slides": [ ... ]
}
```

### 2-3 單頁 Slide 結構

```json
{
  "slide_number": 3,
  "layout_type": "bullets_with_table",
  "title": "Q2 營收與核心效能比較",
  "speaker_notes": "向長官匯報時，請特別強調 Q2 成本下降的兩大關鍵因素...",
  "content": {
    "bullets": [
      "整體成長 15%",
      "三個區域均達標"
    ],
    "markdown_table": "| 項目 | Q1 | Q2 |\n|---|---|---|\n| 營收 | 100 | 115 |\n| 成本 | 80 | 74 |",
    "mermaid": "flowchart LR\n  A[開始] --> B[審核]\n  B --> C{通過?}\n  C -->|是| D[發布]\n  C -->|否| E[退回]"
  }
}
```

> 注意：`mermaid` 與 `markdown_table` 在同一頁內不會並存，依 `layout_type` 決定使用哪個欄位。

### 2-4 Pydantic 驗證規則

**單頁 Slide 層級驗證：**

- `layout_type` 必須在列舉值內
- `bullets` 若存在，不可為空 list
- `markdown_table` 若存在，第一行必須包含 `|`
- `mermaid` 若存在，開頭必須是以下合法圖表類型關鍵字之一：
  - `flowchart`、`sequenceDiagram`、`classDiagram`、`stateDiagram-v2`、`erDiagram`
  - 本專案僅支援上述 5 種類型，其餘類型（gantt、pie、mindmap 等）不在範圍內
- `slide_number` 必須為正整數
- 使用 Pydantic `model_validator` 實作條件式欄位驗證：
  - `table_only` 必須有 `markdown_table`，不可有 `mermaid`
  - `diagram_only` 必須有 `mermaid`，不可有 `markdown_table`
  - `bullets_with_table` 必須同時有 `bullets` + `markdown_table`
  - `bullets_with_diagram` 必須同時有 `bullets` + `mermaid`
  - `bullets_only` 必須有 `bullets`，不可有 `markdown_table` 或 `mermaid`
  - `title_slide` / `section_divider` 不可有 `bullets`、`markdown_table`、`mermaid`

**Presentation 層級驗證（跨 slide 檢查）：**

- `slide_number` 在所有 slides 中不可重複
- `slides` 不可為空 list

---

## 階段三：LLM 呼叫抽象層（src/llm_client.py）

### 3-1 設計目的

將 AI 呼叫邏輯與業務邏輯解耦，支援在不同環境（家用 / 公司）切換不同的 LLM backend。

> 公司 API key 每次申請僅能使用 7 天，需注意 key 過期的錯誤處理。

### 3-2 統一介面

```python
class LLMClient:
    """LLM 呼叫統一介面"""

    def generate(self, prompt: str) -> str:
        """傳入 prompt，回傳 LLM 純文字回應"""
        ...
```

### 3-3 Backend 切換機制

透過環境變數 `LLM_BACKEND` 切換，支援的 backend：

| 環境變數值 | 說明 | 必要環境變數 |
|---|---|---|
| `gemini` | Google Gemini API（家用開發） | `GEMINI_API_KEY` |
| `azure_openai` | Azure OpenAI（公司環境） | `AZURE_OPENAI_ENDPOINT`、`AZURE_OPENAI_KEY` |

### 3-4 設定方式

所有 API key 與設定皆透過環境變數或 `.env` 檔案提供，禁止寫在程式碼中。

```bash
# .env 範例（此檔案不納入版控）
LLM_BACKEND=gemini
GEMINI_API_KEY=your-key-here
```

### 3-5 錯誤處理

- API key 過期或無效 -> 明確的錯誤訊息提示使用者重新申請
- 網路連線失敗 -> 記錄 log 並拋出例外
- LLM 回應逾時 -> 設定合理 timeout（預設 60 秒），逾時拋出例外

---

## 階段四：撰寫 SKILL Prompt

### 4-1 skills/json_outline.md（文字內容 -> JSON）

Prompt 結構：

1. **角色設定**
   - 你是一個企業簡報結構規劃專家
   - 只輸出 JSON，不輸出任何其他文字、說明、或 markdown code block 包裝
   - 不要在 JSON 前後加 ` ```json ` 或 ` ``` `

2. **Schema 說明**
   - 完整列出所有 `layout_type` 及對應的 `content` 欄位
   - 說明 `markdown_table` 格式：用 `\n` 換行的單行 string
   - 說明 `mermaid` 格式：用 `\n` 換行的單行 string，僅用於簡易流程圖
   - 說明何時選用 `mermaid`：步驟流程、決策分支、狀態轉換

3. **speaker_notes 規則**
   - 使用繁體中文
   - 口語化，適合對長官報告的語氣
   - 補充頁面上沒有寫出的背景資訊或注意事項

4. **Few-shot 範例**
   - 提供一段輸入文字（約 200 字的業務說明）
   - 對應完整的 JSON 輸出（3~4 頁 slide）
   - 涵蓋 `bullets_with_table` 和 `bullets_only` 各一個範例

5. **輸入佔位符**
   - 最後一行：`請將以下內容轉換為簡報 JSON：\n{USER_INPUT}`

### 4-2 skills/mermaid_diagram.md（草圖描述 -> Mermaid）

Prompt 結構：

1. **角色設定**
   - 你是流程圖專家
   - 只輸出 mermaid 語法，不輸出任何其他文字
   - 不要加 ` ```mermaid ` 包裝

2. **圖表類型選擇規則**

   | 使用情境 | 圖表類型 |
   |---|---|
   | 流程步驟、決策分支 | `flowchart LR` 或 `flowchart TD` |
   | 系統互動、API 呼叫 | `sequenceDiagram` |
   | 狀態轉換 | `stateDiagram-v2` |
   | 架構、元件關係 | `flowchart TB` |
   | 資料庫關聯 | `erDiagram` |

3. **節點命名規則**
   - 節點 ID 使用英文（避免 mmdc 中文 ID 渲染問題）
   - 節點 label（方括號內）可用中文
   - 範例：`A[開始]`、`B[資料驗證]`、`C{通過?}`

4. **Few-shot 範例**
   - 輸入：「使用者送出申請 -> 系統驗證 -> 主管審核 -> 通過發通知、不通過退回」
   - 輸出：對應的 `flowchart LR` mermaid 語法

5. **輸入佔位符**
   - 最後一行：`請將以下草圖描述轉換為 mermaid 語法：\n{USER_INPUT}`

---

## 階段五：mmdc 設定（config/mermaid.json）

### 5-1 設定項目

```json
{
  "theme": "base",
  "themeVariables": {
    "primaryColor": "#005BAC",
    "primaryTextColor": "#FFFFFF",
    "primaryBorderColor": "#003F7D",
    "lineColor": "#333333",
    "secondaryColor": "#E8F0FA",
    "fontFamily": "Noto Sans TC, Microsoft JhengHei, sans-serif",
    "fontSize": "16px"
  }
}
```

> 顏色與字型請依公司視覺規範調整。
> mmdc 在公司環境已測試通過（PNG / SVG 皆可正常產生）。

### 5-2 mmdc 雙輸出指令

```bash
# 輸出 SVG（母檔，供手動微調）
mmdc -i input/diagram.mmd -o output/diagram.svg -c config/mermaid.json

# 輸出 PNG（供 python-pptx 插入，-s 3 為 3 倍解析度）
mmdc -i input/diagram.mmd -o output/diagram.png -c config/mermaid.json -s 3
```

---

## 階段六：JSON 驗證與 Retry（src/validate.py）

### 6-1 處理流程

```
AI 輸出字串（透過 LLMClient）
    |
嘗試 json.loads()
    |-- 失敗 -> 擷取錯誤訊息 -> 組成 retry prompt -> 透過 LLMClient 重新呼叫 -> 回到頂端（最多 3 次）
    +-- 成功 -> Pydantic 驗證
                |-- 失敗 -> 擷取 ValidationError -> 組成 retry prompt -> 透過 LLMClient 重新呼叫（最多 3 次）
                +-- 成功 -> 回傳驗證後的物件
```

### 6-2 Retry Prompt 範本

```
上一次輸出的 JSON 格式有誤，錯誤訊息如下：
{ERROR_MESSAGE}

請嚴格按照以下 Schema 重新輸出，只輸出 JSON，不要有任何其他文字：
{SCHEMA_DEFINITION}

原始輸入內容：
{ORIGINAL_INPUT}
```

### 6-3 超過重試上限的處理

- 記錄錯誤 log（包含原始輸入、AI 輸出、錯誤訊息）
- 拋出例外，停止該份簡報的生成
- 不靜默失敗

---

## 階段七：build_diagram.py（Mermaid -> PNG/SVG）

### 7-1 處理邏輯

1. 從 JSON 的 `content.mermaid` 欄位讀取 mermaid string
2. 將 `\n` 還原為真正的換行，寫入暫存 `.mmd` 檔
3. 呼叫 mmdc CLI，同時輸出 `.svg` 和 `.png`
4. 回傳 `.png` 路徑供 `build_pptx.py` 使用，`.svg` 存檔備用
5. 清理暫存 `.mmd` 檔

### 7-2 錯誤處理

- mmdc 執行失敗（exit code 不為 0）-> 記錄 stderr log，跳過該圖表，slide 改用 `bullets_only` layout 繼續生成
- 不因單一圖表失敗中斷整份簡報

---

## 階段八：build_pptx.py（JSON -> .pptx）

### 8-1 模板載入

```python
prs = Presentation("config/template.pptx")
```

> 使用相對路徑，CLI 執行時從專案根目錄啟動。
> 先用 `python-pptx` 列印模板內所有 layout 名稱與 placeholder index，確認對應關係後寫死在設定檔。

### 8-2 各 layout_type 處理邏輯

| layout_type | 處理方式 |
|---|---|
| `title_slide` | 填入 title placeholder、subtitle placeholder |
| `section_divider` | 填入 title placeholder |
| `bullets_only` | 填入 title、將 bullets list 逐行填入 content placeholder |
| `table_only` | 解析 markdown_table -> 建立 python-pptx Table 物件 |
| `bullets_with_table` | 同上，bullets 填左欄 placeholder，table 填右欄 placeholder |
| `diagram_only` | 呼叫 build_diagram.py -> 取得 PNG -> add_picture() |
| `bullets_with_diagram` | bullets 填左欄，PNG 插入右欄 |

### 8-3 markdown_table 解析

使用純 Python 實作的 `table_parser.py` 解析 markdown 表格 string，不依賴任何外部套件。

**src/table_parser.py 核心邏輯：**

```python
def parse_markdown_table(md_table: str) -> tuple[list[str], list[list[str]]]:
    """
    解析 markdown 格式的表格字串。
    回傳 (headers, rows)，其中 headers 為欄位名稱 list，
    rows 為二維 list，每個元素為該格的文字內容。
    """
    lines = [
        line.strip()
        for line in md_table.strip().split("\n")
        if line.strip()
    ]

    # 至少要有 header + separator + 1 row
    if len(lines) < 3:
        raise ValueError("markdown table 至少需要 3 行（header + separator + data）")

    # 解析 header
    headers = [
        cell.strip()
        for cell in lines[0].strip("|").split("|")
    ]

    # 跳過 separator（第 2 行），解析資料列
    rows = []
    for line in lines[2:]:
        cells = [
            cell.strip()
            for cell in line.strip("|").split("|")
        ]
        rows.append(cells)

    return headers, rows
```

解析後逐格填入 python-pptx Table。

表格樣式設定（每個 cell 需個別設定，建議包裝成 helper function）：

- 標題列：背景色使用公司主色、文字白色、粗體
- 資料列：交替底色（白 / 淺灰）
- 字型、字級依公司模板規範

### 8-4 speaker_notes 填入

```python
slide.notes_slide.notes_text_frame.text = slide_data.speaker_notes
```

### 8-5 圖片插入位置

- `diagram_only`：置中，寬度佔投影片 70%，保持長寬比
- `bullets_with_diagram`：右半區塊，寬度佔投影片 45%

---

## 階段九：main.py（CLI 統一入口）

### 9-1 使用方式

```bash
# 完整流程：文字稿 -> PPTX
python -m src.main --input input/briefing.txt --output output/report.pptx

# 只生成 mermaid 圖表（手動輸入 mermaid string）
python -m src.main --diagram input/flow.mmd --output output/flow.png

# 從現有 JSON 直接生成 PPTX（跳過 AI 步驟）
python -m src.main --json input/slides.json --output output/report.pptx
```

### 9-2 執行順序

```
1. 讀取輸入文字
2. 初始化 LLMClient（依環境變數決定 backend）
3. 透過 LLMClient 呼叫 AI（使用 json_outline SKILL）
4. validate.py 驗證 JSON（含 retry，retry 也透過 LLMClient）
5. 對每個含 mermaid 的 slide，呼叫 build_diagram.py
6. build_pptx.py 組裝整份 PPTX
7. 輸出至 output/ 目錄
8. 印出完成訊息（共幾頁、耗時、輸出路徑）
```

---

## 階段十：測試策略

### 10-1 測試框架

使用 `pytest`，測試檔案放在 `tests/` 目錄。

### 10-2 各模組測試範圍

| 測試檔案 | 測試目標 | 測試案例 |
|---|---|---|
| `test_schema.py` | Pydantic Schema 驗證 | 各 layout_type 的合法 JSON、欄位缺漏、類型錯誤、slide_number 重複、條件式欄位不一致 |
| `test_table_parser.py` | markdown table 解析 | 正常表格、少於 3 行、空格不一致、中文內容、欄位數量不一致 |
| `test_build_pptx.py` | PPTX 生成整合測試 | 每種 layout_type 各一個測試用 JSON，驗證產出的 .pptx 是否可正常開啟、slide 數量正確 |
| `test_build_diagram.py` | Mermaid 渲染測試 | 各種圖表類型的渲染、mmdc 失敗時的 fallback 行為 |

### 10-3 執行方式

```bash
# 執行所有測試
python -m pytest tests/ -v

# 執行單一模組測試
python -m pytest tests/test_schema.py -v
```

### 10-4 CI 注意事項

- `test_build_diagram.py` 依賴 mmdc 環境，在未安裝 mmdc 的環境中應自動 skip
- `test_build_pptx.py` 依賴 `config/template.pptx`，測試時使用測試專用的最小模板

---

## 階段十一：Git 版本控制

### 納入版控的檔案

```
docs/           <- 實作計畫文件
skills/         <- Prompt 版本演進
schemas/        <- Schema 變更紀錄
config/         <- mermaid.json 樣式調整（不含 template.pptx）
src/            <- 程式邏輯
tests/          <- 測試程式碼
pyproject.toml  <- 依賴定義
```

### .gitignore

```gitignore
# 公司機密模板
config/template.pptx

# 產出檔案
output/*.pptx
output/*.png
output/*.svg
output/*.mmd

# Python 虛擬環境與快取
.venv/
__pycache__/
*.pyc
.pytest_cache/

# 敏感設定
.env
```

### 版控優點

- `git diff skills/json_outline.md` 追蹤 Prompt 調整歷史
- `git diff output/slides.json` 看每次簡報內容改了哪幾頁
- `git diff config/mermaid.json` 追蹤色系調整

---

## 實作優先順序

| 優先序 | 項目 | 原因 |
|---|---|---|
| 1 | pyproject.toml + 虛擬環境 | 專案骨架，所有開發的起點 |
| 2 | Schema 定義（Pydantic） | 所有後續工作的資料基礎 |
| 3 | table_parser.py + 測試 | 無外部依賴，可獨立開發與驗證 |
| 4 | LLM Client 抽象層 | validate.py 和 main.py 都依賴它 |
| 5 | mmdc 雙輸出測試 | 確認公司環境無問題 |
| 6 | build_pptx.py 核心邏輯 | 最複雜，需要最多測試 |
| 7 | validate.py retry 機制 | 保護生產流程穩定性 |
| 8 | SKILL Prompt 撰寫與調校 | 依 Schema 撰寫，需反覆測試 |
| 9 | main.py CLI 整合 | 最後串接 |
| 10 | 完整測試與驗收 | 確保各模組整合正確 |

---

## 依賴清單

| 套件 | 版本 | 用途 | 備註 |
|---|---|---|---|
| `python-pptx` | ==1.0.2 | 生成 PPTX | 鎖定版本，定期 pip-audit 掃描 |
| `pydantic` | >=2.0,<3.0 | JSON schema 驗證 | 活躍維護 |
| `pytest` | >=8.0（dev） | 測試框架 | 僅開發環境 |
| `pip-audit` | latest（dev） | 依賴安全掃描 | 僅開發環境 |

> 核心 runtime 依賴僅 2 個套件，供應鏈風險最小化。
> mmdc 為 Node.js 工具，獨立於 Python 環境，不在 pyproject.toml 中管理。

---

## 已知風險與對策

| 風險 | 對策 |
|---|---|
| python-pptx 不支援 SVG 插入 | mmdc 同時輸出 PNG，python-pptx 使用 PNG |
| python-pptx 維護活動低 | 鎖定版本 + pip-audit 定期掃描，預留內部 fork 可能性 |
| AI 輸出 JSON 格式錯誤 | Pydantic 驗證 + 最多 3 次 auto-retry |
| mmdc 中文字型渲染異常 | config.json 指定已安裝的中文字型，節點 ID 用英文 |
| 公司模板 placeholder 對應不明 | 先用腳本列印所有 placeholder index 和名稱再撰寫邏輯 |
| mmdc 需要 Chromium headless | 公司環境已測試通過（PNG / SVG 皆可正常產生） |
| 公司 API key 每 7 天過期 | LLM Client 明確處理 key 過期錯誤，提示使用者重新申請 |
| 不同環境使用不同 LLM | LLM Client 抽象層透過環境變數切換 backend |
