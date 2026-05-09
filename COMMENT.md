很簡單，只要兩步：

## 移植回公司的操作步驟

```
步驟 1: 跑掃描腳本（已經有了）
  把公司模板放到 config/template.pptx
  執行 python scan_template.py
  看輸出結果

步驟 2: 更新 placeholder 對應設定
  改一個 config 檔就好（不用改程式碼）
```

## 我的建議：批次 3 架構設計

為了讓換模板不用改 code，我建議 build_pptx.py 讀取一個 **template_map.json** 來決定 placeholder 對應關係：

```json
{
    "title_slide": {
        "layout_name": "Cover Slide layout",
        "title_idx": 10,
        "subtitle_idx": 11
    },
    "section_divider": {
        "layout_name": "Section Break Layout",
        "title_idx": 10,
        "subtitle_idx": 11
    },
    "bullets_only": {
        "layout_name": "Basic Layout",
        "title_idx": 10,
        "subtitle_idx": 11
    },
    "table_only": {
        "layout_name": "Basic Layout",
        "title_idx": 10,
        "subtitle_idx": 11
    },
    "bullets_with_table": {
        "layout_name": "Basic Layout",
        "title_idx": 10,
        "subtitle_idx": 11
    },
    "diagram_only": {
        "layout_name": "Basic Layout",
        "title_idx": 10,
        "subtitle_idx": 11
    },
    "bullets_with_diagram": {
        "layout_name": "Basic Layout",
        "title_idx": 10,
        "subtitle_idx": 11
    }
}
```

**移植回公司時：**
1. 把公司模板放進 `config/template.pptx`
2. 跑 `python scan_template.py`，看公司模板有哪些 layout 和 placeholder
3. 更新 `config/template_map.json` 裡的 `layout_name` 和 `*_idx` 值
4. 完成，不用動任何 Python 程式碼

**如果公司模板有真正的 content placeholder**（很多公司模板都有 idx=1 的 body placeholder），那 bullets 就不用塞進副標題，直接填進 body，排版效果會好很多。到時候只要在 json 加個 `"body_idx": 1` 就行。

---

所以回到你的問題 -- **可以叫 Sonnet 寫批次 3 了**。我會把以下資訊給它：

1. 當前模板的 placeholder 結構（idx=10 標題、idx=11 副標題、沒有 body）
2. 要求 build_pptx.py 讀取 `template_map.json`，不可硬寫 placeholder index
3. 沒有 body placeholder 的情況下，用 `add_textbox()` 和 `add_table()` 手動排版
4. 產出 `scan_template.py` 的改良版（可自動生成 template_map.json 初稿）

要我整理成 prompt 給你貼去 Sonnet？