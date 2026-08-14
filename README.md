# 傑生工程工作室

傑生工程工作室專注於嵌入式系統開發，結合 Python、硬體控制與資料管理，展示從裝置整合、感測資料處理到後台管理的完整流程。這個專案可用來呈現嵌入式應用的實作成果，也適合延伸成教學展示或作品集內容。

## 啟動方式

```powershell
python server.py
```

開啟後台網址：

```text
http://127.0.0.1:8013/
```

## Render PostgreSQL 持久化

正式 Render 服務必須設定 `DATABASE_URL` 為同一 Render workspace 內 PostgreSQL
提供的 **Internal Database URL**。Render 環境缺少此變數時，程式會直接停止，
不會改用空白 SQLite。

Render 設定：

```text
Build Command: pip install -r requirements.txt
Pre-Deploy Command: python migrate.py
Start Command: python server.py
```

請勿在 Build、Pre-Deploy 或 Start Command 執行 `seed.py`。Migration 只建立缺少的
資料表、欄位及索引，不會清除或重建資料。若平台方案沒有 Pre-Deploy Command，
`server.py` 啟動時仍會先安全執行相同的版本化 migration，失敗時不會啟動網站。

本機開發未設定 `DATABASE_URL` 時仍使用 `data/studio_shop.db`，此檔及其備份均已被
Git 忽略。只有初始化全新空資料庫時，才可手動執行：

```powershell
python seed.py
```

### 一次性搬移既有 SQLite

先備份 Render 上目前的 SQLite，再於可連線 PostgreSQL 的環境設定 `DATABASE_URL`。
若在本機執行，需暫時使用 Render PostgreSQL 的 External Database URL；搬移完成後
應移除本機環境變數，Render Web Service 本身仍使用 Internal Database URL。

```powershell
python scripts/migrate_sqlite_to_postgres.py --sqlite data/studio_shop.db
```

工具會再次建立 timestamp 備份、拒絕寫入非空 PostgreSQL、保留原 ID 與關聯，
並核對各資料表筆數、外鍵及訂單金額。工具不會由網站啟動流程自動執行，也不會
刪除 SQLite 或備份。

## 專案特色

- 嵌入式系統應用展示
- Python 與 SQLite 資料整合
- 裝置資料收集與管理介面
- 適合作品集、教學與技術展示

## AI 客服設定與成本控制

AI 客服使用 OpenAI Responses API。API Key 只可放在本機 `.env` 或 Render 的
Environment Variables，不可寫入 HTML、JavaScript、GitHub 或公開設定檔。

Render 建議設定：

```text
OPENAI_API_KEY=你的 OpenAI API Key
OPENAI_MODEL=gpt-5.6-luna
OPENAI_TIMEOUT_SECONDS=20
AI_CHAT_ENABLED=true
AI_MAX_MESSAGE_LENGTH=500
AI_MAX_OUTPUT_TOKENS=300
AI_RATE_LIMIT_PER_MINUTE=5
AI_RATE_LIMIT_PER_HOUR=20
AI_HISTORY_MAX_ROUNDS=4
```

要立即停止新的 AI API 呼叫，可將 `AI_CHAT_ENABLED` 設為 `false` 並重新部署／重啟
服務。降低 `AI_MAX_OUTPUT_TOKENS`、限制詢問次數及縮短對話歷史，可以進一步減少
token 使用量。伺服器會以 `[ai-chat-usage]` 紀錄每次成功回覆的 input、output 與
total tokens，但不記錄 API Key、聊天內容或付款 Secret。

網站端限制只能降低濫用與意外支出，不能保證每月費用一定低於特定金額。若目標是
每月約 US$5，仍需自行登入 OpenAI Platform，為專用 Project 設定可用的 Budget／
Spend Limit，並定期查看 Usage 與 Billing。不同帳戶可用的預算控制項可能不同，
應以 OpenAI Platform 當下顯示的設定為準。
