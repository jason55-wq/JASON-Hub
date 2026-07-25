# PayPal Checkout 設定與維運

PayPal 使用官方 JavaScript SDK 與 Orders v2 API。瀏覽器只取得 Client ID；
Client Secret 與 Access Token 僅由後端環境變數讀取。建立訂單與 Capture 都由後端執行，
商品價格及總額會重新從資料庫計算。

## Render 環境變數

```text
PAYPAL_CLIENT_ID=
PAYPAL_CLIENT_SECRET=
PAYPAL_MODE=sandbox
PAYPAL_CURRENCY=USD
PAYPAL_WEBHOOK_ID=
PAYPAL_TWD_PER_USD=
PAYPAL_TIMEOUT_SECONDS=15
BASE_URL=https://jason-hub.onrender.com
```

網站商品價格是新台幣。`PAYPAL_CURRENCY=USD` 時必須設定
`PAYPAL_TWD_PER_USD`，例如 Sandbox 測試可暫設 `30`。正式環境應使用商家核准的固定匯率，
變更匯率只會影響新建立的 PayPal 訂單。若改用 `PAYPAL_CURRENCY=TWD`，不需要換算率。

## Webhook

PayPal Developer Dashboard 的 webhook URL：

```text
https://jason-hub.onrender.com/api/paypal/webhook
```

訂閱事件：

```text
PAYMENT.CAPTURE.COMPLETED
PAYMENT.CAPTURE.DENIED
PAYMENT.CAPTURE.REFUNDED
```

## 本機 Sandbox 測試

1. 複製 `.env.example` 的 PayPal 變數到本機環境（不要提交 `.env`）。
2. 將 `BASE_URL` 設為本機 HTTPS tunnel URL；PayPal webhook 無法呼叫一般 localhost。
3. 執行 `python migrate.py`。
4. 執行 `python server.py`，登入已核准帳號後使用 PayPal Sandbox 買家付款。
5. 執行 `python -m unittest discover -s tests -v`。

## Render Sandbox 測試

1. 在 Render 設定上述 Sandbox 環境變數。
2. 保留 Pre-Deploy Command `python migrate.py`；migration 只新增欄位、索引和 webhook event table。
3. 在 PayPal Sandbox App 設定 webhook URL 與事件，將 Webhook ID 寫入 Render。
4. 部署後用 Sandbox 買家測試成功、取消、失敗與 webhook 重送。

## 正式環境切換

1. 建立並核准 PayPal Live App，取得 Live Client ID、Secret 和 Webhook ID。
2. 將 `PAYPAL_MODE` 改為 `live`，換成所有 Live credentials。
3. 確認 `BASE_URL` 是正式 HTTPS 網址並設定 Live webhook。
4. 確認正式 USD 換算率後，以小額真實交易驗證，再開放使用者。

## 回復原版本

切回功能導入前的 Git commit `d3184c6` 並重新部署。migration 新增的欄位與
`paypal_webhook_events` table 可以保留，不影響舊程式；不需要也不應刪除或重建資料庫。
