# crypto-monitor

Streamlit 版 Heikin-Ashi 階梯型態監控工具。

## 功能

- Pionex 1D／4H K 線
- Heikin-Ashi 黃紫階梯
- 日線 BB 中軌
- 型態分類、機械分數與三燈狀態
- 日線均K黃紫切換分界價
- 下載並同步 `snapshot_ai.json`

## snapshot_ai.json

供 ChatGPT 分析的精簡檔案，只保留四大區塊：

1. `batch`：批次時間、hash、schema、數量與篩選資訊
2. `breadth`：Ladder 紅黃綠、日線黃紫、4H 組合與中軌廣度
3. `records`：每顆幣的中軌、分界、階梯、型態、板塊與分數
4. `groups`：突破回踩、第一／第二階、4H 觸發與候選分組

不再輸出重複的完整表格、20 日原始 open／close 陣列與逐幣說明文字；JSON 以緊湊格式輸出以降低檔案大小。

## Streamlit Community Cloud 部署

1. 將本資料夾內所有檔案上傳到 GitHub 儲存庫根目錄。
2. 在 Streamlit Community Cloud 建立 App。
3. Repository：`adam1984smasher-design/crypto-monitor`
4. Branch：`main`
5. Main file path：`main.py`
6. 點擊 Deploy。

## 必要檔案

```text
main.py
get.py
github_sync.py
ha_threshold.py
scoring_rules.py
symbols_config.py
sector_config.py
pattern_options.py
requirements.txt
.streamlit/config.toml
```

## GitHub 自動同步 Secrets

```toml
GITHUB_TOKEN = "..."
GITHUB_REPOSITORY = "adam1984smasher-design/crypto-monitor"
GITHUB_BRANCH = "main"
GITHUB_AI_SNAPSHOT_PATH = "snapshot_ai.json"
```

`GITHUB_AI_SNAPSHOT_PATH` 未設定時，預設仍會寫入儲存庫根目錄的
`snapshot_ai.json`。

## 注意

- 不需要上傳 `.venv`、`__pycache__` 或 Windows `.bat`。
- 程式會即時呼叫 Pionex 公開 API，因此部署環境需要外網連線。
- `snapshot_ai.json` 由 Streamlit 執行時動態產生並同步至 GitHub。
