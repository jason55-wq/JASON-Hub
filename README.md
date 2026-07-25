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
