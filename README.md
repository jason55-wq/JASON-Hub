# Studio Member Shop

工作室會員制電商網站，使用 Python 標準庫與 SQLite，不需要額外安裝套件。

## 啟動

```powershell
python server.py
```

開啟：

```text
http://127.0.0.1:8013/
```

## 已包含功能

- 會員申請、登入、登出
- 會員審核：`pending`、`approved`、`rejected`
- 管理員與一般會員角色
- 商品新建、編輯、上架、草稿、封存
- 商品資料儲存在 `data/studio_shop.db`
- 購物車與會員下單
- 訂單管理與狀態更新
- 商品庫存扣除
- 已有訂單的商品刪除時會改為封存，保留訂單資料完整性
