const state = {
  user: null,
  products: [],
  cart: loadCart(),
  visitorCount: 0,
  readMode: "project",
  csrfToken: null,
  paypalCheckoutToken: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const DEFAULT_PRODUCT_IMAGE = window.DEFAULT_PRODUCT_IMAGE || "/static/vios.png";

function loadCart() {
  try {
    return JSON.parse(localStorage.getItem("studio_cart") || "[]");
  } catch {
    return [];
  }
}

function saveCart() {
  localStorage.setItem("studio_cart", JSON.stringify(state.cart));
  renderCart();
}

function money(value) {
  return `NT$${Number(value || 0).toLocaleString("zh-TW")}`;
}

function orderReviewLabel(status) {
  if (status === "approved") return "已審核";
  if (status === "rejected") return "已拒絕";
  if (status === "pending") return "待審核";
  return status || "未知";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function excerpt(value, length = 140) {
  const text = String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length <= length) return text;
  return `${text.slice(0, length - 1)}…`;
}

function openPreview(url) {
  if (!url) return;
  window.open(url, "_blank", "noreferrer");
}

function productPreviewUrls(product) {
  const previewUrl = product.preview_url || "";
  const previewUrls = previewUrl ? [previewUrl] : [];
  if (
    product.name === "AT1筆記本(精華筆記)" &&
    !previewUrls.includes("/static/XAT1_VC_GNB.pdf")
  ) {
    previewUrls.push("/static/XAT1_VC_GNB.pdf");
  }
  return previewUrls;
}

async function api(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(state.csrfToken && method !== "GET" ? { "X-CSRF-Token": state.csrfToken } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

function notify(message) {
  const box = $("#notice");
  if (!box) return;
  box.textContent = message;
  box.classList.remove("hidden");
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => box.classList.add("hidden"), 3500);
}

function showView(name) {
  $$(".view").forEach((view) => view.classList.remove("active"));
  const target = $(`#${name}View`);
  if (target) target.classList.add("active");
  if (name === "orders") loadOrders();
  if (name === "admin") loadAdmin();
}

function syncChrome() {
  const isAuthed = Boolean(state.user);
  const isAdmin = state.user?.role === "admin" && state.user?.status === "approved";

  $$(".guest-only").forEach((el) => el.classList.toggle("hidden", isAuthed));
  $$(".auth-only").forEach((el) => el.classList.toggle("hidden", !isAuthed));
  $$(".admin-only").forEach((el) => el.classList.toggle("hidden", !isAdmin));

  const badge = $("#userBadge");
  if (badge) {
    if (state.user) {
      const statusLabel =
        state.user.status === "approved"
          ? "已通過"
          : state.user.status === "rejected"
            ? "已拒絕"
            : "待審核";
      const roleLabel = state.user.role === "admin" ? "管理員" : "會員";
      badge.textContent = `${state.user.username} ｜ ${statusLabel} ｜ ${roleLabel}`;
    } else {
      badge.textContent = "";
    }
  }

  const heroStatus = $("#heroStatus");
  if (heroStatus) {
    heroStatus.textContent = state.user
      ? state.user.status === "approved"
        ? state.user.role === "admin"
          ? "管理員已登入，可檢視訂單"
          : "會員已通過審核"
        : "會員待審核"
      : "可直接下單，不必先登入";
  }
}

async function loadMe() {
  const data = await api("/api/me");
  state.user = data.user;
  state.csrfToken = data.csrf_token || null;
  syncChrome();
}

async function loadProducts(admin = false) {
  const data = await api(`/api/products${admin ? "?admin=1" : ""}`);
  if (!admin) {
    state.products = data.products || [];
  }
  return data.products || [];
}

async function loadVisitStats() {
  const data = await api("/api/visit-stats");
  state.visitorCount = Number(data.visits || 0);
  renderVisitStats();
}

function renderVisitStats() {
  const count = $("#visitorCount");
  if (count) count.textContent = state.visitorCount.toLocaleString("zh-TW");
}

function setReadMode(mode) {
  state.readMode = mode === "product" ? "product" : "project";
  renderReadContent();
}

function renderReadContent() {
  const wrap = $("#readContent");
  if (!wrap) return;

  $$(".mode-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.readMode === state.readMode);
  });

  const projectContent = `
    <article class="story-card story-card-project">
      <div class="story-body">
        <div class="story-head">
          <span class="tag">專案介紹</span>
          <span class="tag">DIY WIN10 聲控電腦 VIOS</span>
        </div>
        <h3>把電腦操作變成人人都能學會的聲控系統</h3>
        <p>VIOS 是一個把語音操作、學習流程與 Windows 控制整合在一起的專案介紹頁。這個專案的重點不只是展示功能，而是把一套可學、可改、可延伸的 Python 工具，整理成更容易理解的實作範例。</p>
        <p>VIOS 想解決的是「學會工具之後，能不能真的做出自己的作品」這件事。它從基礎的語音引導開始，讓初學者可以按步驟操作，再進一步延伸到個別練習、成果輸出，以及更多生活與學習情境的應用。像是語音輸入、語音回應輸出、MP3 檔案輸出、通訊介面、網頁圖形下載、一鍵操作與聲控連結等，都是這個系統希望帶給使用者的核心體驗。</p>
        <p>如果你想看更完整的募資脈絡、理念與介紹，可以前往嘖嘖頁面了解：<br>https://www.zeczec.com/projects/diy-win10-vios</p>
        <p>這不是單純的販售頁，而是一個希望讓更多人理解「如何把電腦操作變成可學習、可擴充的系統」的專案介紹。</p>
      </div>
    </article>
    <article class="story-card story-card-project">
      <div class="story-body">
        <div class="story-head">
          <span class="tag">AI 架站</span>
          <span class="tag">新手指南</span>
        </div>
        <h3>AI 架站完整指南｜零基礎也能打造自己的網站</h3>

        <h4>為什麼現在越來越多人開始使用 AI 架站？</h4>
        <p>近年來，人工智慧（AI）發展快速，網站開發的方式也產生了巨大的改變。過去建立一個網站，往往需要學習 HTML、CSS、JavaScript、資料庫、伺服器部署等技術，對許多初學者而言門檻相當高。</p>
        <p>現在，透過 AI 工具的協助，即使沒有完整的程式設計背景，也能快速完成網站開發，將更多時間投入在產品內容、品牌經營與行銷推廣。</p>

        <h4>AI 可以協助完成哪些工作？</h4>
        <p>AI 不只是幫你寫程式，更能參與整個網站開發流程，例如：</p>
        <ul>
          <li>網站架構規劃</li>
          <li>HTML、CSS、JavaScript 撰寫</li>
          <li>Python、Flask 等後端程式開發</li>
          <li>資料庫設計與修改</li>
          <li>登入、會員系統</li>
          <li>商品展示頁</li>
          <li>購物車功能</li>
          <li>金流串接</li>
          <li>網站除錯與錯誤排除</li>
          <li>UI/UX 優化建議</li>
          <li>SEO 內容撰寫</li>
          <li>教學文件與操作說明</li>
        </ul>
        <p>透過 AI，可以大幅減少重複性的開發工作，提升整體效率。</p>

        <h4>AI 架站並不是按一下就完成</h4>
        <p>很多人認為 AI 可以一鍵完成網站，其實真正的開發流程仍需要開發者與 AI 持續合作。</p>
        <p>一個完整網站通常需要經過：</p>
        <ol>
          <li>規劃網站功能</li>
          <li>撰寫提示詞（Prompt）</li>
          <li>AI 生成程式碼</li>
          <li>測試功能</li>
          <li>修正錯誤</li>
          <li>優化介面</li>
          <li>部署到網路</li>
          <li>持續更新與維護</li>
        </ol>
        <p>因此，AI 更像是一位全天候的開發助手，而不是完全取代開發者。</p>

        <h4>AI 架站有哪些優點？</h4>
        <h5>開發速度更快</h5>
        <p>許多原本需要數天甚至數週完成的功能，現在可能只需要幾個小時即可完成初版。</p>
        <h5>降低學習門檻</h5>
        <p>即使沒有完整的資訊背景，也能一步一步學習網站開發。</p>
        <h5>快速修改功能</h5>
        <p>當需要新增頁面、修改樣式或增加功能時，只需描述需求，AI 即可協助產生新的程式碼。</p>
        <h5>學習效率更高</h5>
        <p>AI 不只是提供答案，也能解釋每段程式碼的用途，幫助理解網站運作原理。</p>

        <h4>AI 架站需要會程式嗎？</h4>
        <p>如果希望建立簡單網站，幾乎不用具備完整的程式能力。</p>
        <p>但若想開發功能較完整的網站，例如：</p>
        <ul>
          <li>電商網站</li>
          <li>會員系統</li>
          <li>金流付款</li>
          <li>後台管理</li>
          <li>API 串接</li>
          <li>雲端部署</li>
        </ul>
        <p>仍建議學習基本的程式設計觀念，才能更有效率地與 AI 協作，也更容易判斷 AI 產生的程式是否符合需求。</p>

        <h4>AI 是工具，不是捷徑</h4>
        <p>AI 能夠協助完成大量工作，但真正決定網站品質的，仍然是開發者的規劃能力、問題分析能力，以及持續優化的態度。</p>
        <p>當你懂得如何提出明確需求、閱讀程式碼、測試功能並修正問題時，AI 將成為非常強大的開發夥伴。</p>

        <h4>結語</h4>
        <p>AI 正在改變網站開發的方式，讓更多人有機會打造屬於自己的網站與品牌。</p>
        <p>無論是個人作品集、企業官網、部落格，或是電商網站，只要善用 AI 工具，再搭配持續學習與實作，每個人都有機會完成自己的網站。</p>
        <p>希望這個網站分享的教學、筆記與經驗，能協助更多初學者了解 AI 架站的流程，少走一些彎路，快速建立自己的第一個網站。</p>
      </div>
    </article>
  `;

  if (state.readMode === "product") {
    const products = state.products.filter((product) => product.status === "active");
    wrap.innerHTML = products.length
      ? `
        <div class="product-grid">
          ${products
            .map((product) => {
              const imageUrl = product.image_url || DEFAULT_PRODUCT_IMAGE;
              return `
                <article class="product-card" onclick="openProductDetail(${product.id})" tabindex="0"
                  onkeydown="if(event.key === 'Enter') openProductDetail(${product.id})">
                  <div class="product-image-wrap">
                    <img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(product.name)}">
                  </div>
                  <div class="product-body">
                    <h3>${escapeHtml(product.name)}</h3>
                    <strong class="price">${money(product.price)}</strong>
                  </div>
                </article>
              `;
            })
            .join("")}
        </div>
      `
      : `<p class="hint">目前沒有可販售的商品。</p>`;
    return;
  }

  wrap.innerHTML = projectContent;
}

function openProductDetail(productId) {
  const product = state.products.find((item) => item.id === productId);
  const overlay = $("#productDetail");
  const content = $("#productDetailContent");
  if (!product || !overlay || !content) return;
  const imageUrl = product.image_url || DEFAULT_PRODUCT_IMAGE;
  const previewLinks = productPreviewUrls(product)
    .map((url) => `<a class="product-preview-button" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">預覽 PDF</a>`)
    .join("");

  content.innerHTML = `
    <div class="product-detail-layout">
      <div class="product-detail-gallery">
        <div class="product-detail-image"><img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(product.name)}"></div>
        <button type="button" class="product-thumb active"><img src="${escapeHtml(imageUrl)}" alt=""></button>
      </div>
      <div class="product-detail-info">
        <h2 id="productDetailTitle">${escapeHtml(product.name)}</h2>
        <div class="product-summary">
          <span>${escapeHtml(product.category || "工作室選品")}</span>
          <i></i>
          <span>庫存 ${Number(product.stock || 0).toLocaleString("zh-TW")} 件</span>
        </div>
        <div class="product-detail-price">${money(product.price)}</div>
        <div class="product-detail-row">
          <span>訂購方式</span>
          <div><strong>選擇數量後加入購物車，即可接續完成訂單</strong><small>送出後將依商品內容與您確認後續資訊</small></div>
        </div>
        <div class="product-detail-row">
          <span>服務說明</span>
          <div><strong>如對內容或訂單有疑問，可透過網站聯絡資訊詢問</strong></div>
        </div>
        <div class="product-detail-row">
          <span>內容介紹</span>
          <div class="product-detail-description">${escapeHtml(product.description || "暫無商品說明").replaceAll("\n", "<br>")}</div>
        </div>
        <div class="product-detail-row">
          <span>數量</span>
          <div class="quantity-picker">
            <button type="button" onclick="changeProductQuantity(-1)">−</button>
            <input id="productDetailQuantity" type="number" value="1" min="1" max="${Number(product.stock || 1)}" aria-label="商品數量">
            <button type="button" onclick="changeProductQuantity(1)">＋</button>
            <small>尚有 ${Number(product.stock || 0).toLocaleString("zh-TW")} 件</small>
          </div>
        </div>
        <div class="product-detail-actions">
          <button type="button" class="add-cart-button" onclick="addDetailProductToCart(${product.id})">加入購物車</button>
          <button type="button" class="buy-now-button" onclick="buyProductNow(${product.id})">立即訂購</button>
          ${previewLinks}
        </div>
      </div>
    </div>`;
  overlay.classList.add("open");
  overlay.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeProductDetail() {
  const overlay = $("#productDetail");
  if (!overlay) return;
  overlay.classList.remove("open");
  overlay.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

function changeProductQuantity(change) {
  const input = $("#productDetailQuantity");
  if (!input) return;
  input.value = Math.min(Number(input.max || 1), Math.max(1, Number(input.value || 1) + change));
}

function detailProductQuantity() {
  return Math.max(1, Number.parseInt($("#productDetailQuantity")?.value || "1", 10) || 1);
}

function addDetailProductToCart(productId) {
  addToCart(productId, detailProductQuantity());
}

function buyProductNow(productId) {
  addToCart(productId, detailProductQuantity());
  closeProductDetail();
  $("#cartDrawer")?.classList.add("open");
}

function addToCart(productId, quantity = 1) {
  const product = state.products.find((item) => item.id === productId);
  if (!product || product.stock <= 0) return;
  const found = state.cart.find((item) => item.product_id === productId);
  const amount = Math.min(Math.max(1, Number(quantity) || 1), Number(product.stock));
  if (found) found.quantity = Math.min(found.quantity + amount, Number(product.stock));
  else state.cart.push({ product_id: productId, quantity: amount });
  saveCart();
  notify("已加入購物車");
}

function changeQty(productId, delta) {
  const item = state.cart.find((entry) => entry.product_id === productId);
  if (!item) return;
  item.quantity += delta;
  if (item.quantity <= 0) {
    state.cart = state.cart.filter((entry) => entry.product_id !== productId);
  }
  saveCart();
}

function removeFromCart(productId) {
  state.cart = state.cart.filter((entry) => entry.product_id !== productId);
  saveCart();
}

function renderCart() {
  const count = $("#cartCount");
  if (count) count.textContent = state.cart.reduce((sum, item) => sum + item.quantity, 0);

  const wrap = $("#cartItems");
  if (!wrap) return;

  let total = 0;
  if (state.cart.length === 0) {
    wrap.innerHTML = `<p class="hint">購物車目前是空的。</p>`;
  } else {
    wrap.innerHTML = state.cart
      .map((item) => {
        const product = state.products.find((p) => p.id === item.product_id);
        if (!product) return "";
        const subtotal = Number(product.price || 0) * item.quantity;
        total += subtotal;
        return `
          <div class="cart-row">
            <strong>${escapeHtml(product.name)}</strong>
            <div class="line">
              <span>${money(product.price)} x ${item.quantity}</span>
              <strong>${money(subtotal)}</strong>
            </div>
            <div class="table-actions">
              <button type="button" onclick="changeQty(${product.id}, -1)">-</button>
              <button type="button" onclick="changeQty(${product.id}, 1)">+</button>
              <button type="button" class="ghost" onclick="removeFromCart(${product.id})">移除</button>
            </div>
          </div>
        `;
      })
      .join("");
  }

  const totalBox = $("#cartTotal");
  if (totalBox) totalBox.textContent = money(total);
}

async function checkout(event) {
  event.preventDefault();
  const checkoutForm = event.currentTarget;
  if (!state.cart.length) {
    notify("請先加入商品");
    return;
  }

  const payload = checkoutPayload(checkoutForm);

  try {
    await api("/api/orders", { method: "POST", body: JSON.stringify(payload) });
    state.cart = [];
    saveCart();
    checkoutForm.reset();
    notify("訂單已送出");
  } catch (error) {
    notify(error.message);
  }
}

function checkoutPayload(checkoutForm) {
  const form = new FormData(checkoutForm);
  return {
    items: state.cart,
    customer_name: String(form.get("customer_name") || "").trim(),
    phone: String(form.get("phone") || "").trim(),
    address: String(form.get("address") || "").trim(),
    note: String(form.get("note") || "").trim(),
  };
}

async function checkoutWithEcpay() {
  const checkoutForm = $("#checkoutForm");
  const button = $("#ecpayCheckoutBtn");
  const hint = $("#paymentHint");
  if (!checkoutForm || !button) return;
  if (!state.cart.length) {
    notify("請先加入商品");
    return;
  }
  if (!checkoutForm.reportValidity()) return;

  button.disabled = true;
  button.textContent = "正在前往付款頁面";
  if (hint) hint.textContent = "正在安全連線至綠界，請勿重複點擊或關閉頁面。";
  const checkoutToken =
    window.crypto?.randomUUID?.() ||
    `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  try {
    const result = await api("/api/ecpay/checkout", {
      method: "POST",
      body: JSON.stringify({
        ...checkoutPayload(checkoutForm),
        checkout_token: checkoutToken,
      }),
    });
    const paymentForm = document.createElement("form");
    paymentForm.method = "POST";
    paymentForm.action = result.payment_url;
    Object.entries(result.parameters || {}).forEach(([name, value]) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = String(value);
      paymentForm.appendChild(input);
    });
    document.body.appendChild(paymentForm);
    state.cart = [];
    saveCart();
    paymentForm.submit();
  } catch (error) {
    button.disabled = false;
    button.textContent = "信用卡付款／前往綠界付款";
    if (hint) hint.textContent = "信用卡資料將在綠界安全付款頁面輸入。";
    notify(error.message);
  }
}

function loadPayPalSdk(config) {
  if (window.paypal) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    const params = new URLSearchParams({
      "client-id": config.client_id,
      currency: config.currency,
      intent: "capture",
      components: "buttons",
    });
    script.src = `https://www.paypal.com/sdk/js?${params}`;
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error("PayPal 付款元件載入失敗"));
    document.head.appendChild(script);
  });
}

async function initPayPal() {
  const container = $("#paypal-button-container");
  const hint = $("#paypalHint");
  if (!container || !hint) return;
  try {
    const config = await api("/api/paypal/config");
    if (!config.enabled) {
      container.innerHTML = "";
      hint.textContent = config.message || "PayPal 國際付款目前無法使用。";
      return;
    }
    await loadPayPalSdk(config);
    hint.textContent = `PayPal 將以 ${config.currency} 收款；金額由伺服器依商品資料重新計算。`;
    window.paypal
      .Buttons({
        style: { layout: "vertical", shape: "rect", label: "paypal" },
        onClick(_data, actions) {
          const form = $("#checkoutForm");
          if (!state.cart.length) {
            notify("請先加入商品");
            return actions.reject();
          }
          if (!form?.reportValidity()) return actions.reject();
          return actions.resolve();
        },
        async createOrder() {
          const form = $("#checkoutForm");
          state.paypalCheckoutToken =
            state.paypalCheckoutToken ||
            window.crypto?.randomUUID?.() ||
            `${Date.now()}-${Math.random().toString(36).slice(2)}`;
          const result = await api("/api/paypal/orders", {
            method: "POST",
            body: JSON.stringify({
              ...checkoutPayload(form),
              checkout_token: state.paypalCheckoutToken,
            }),
          });
          return result.order_id;
        },
        async onApprove(data) {
          hint.textContent = "PayPal 已授權，正在由伺服器核對並完成付款。";
          const result = await api("/api/paypal/orders/capture", {
            method: "POST",
            body: JSON.stringify({ order_id: data.orderID }),
          });
          state.cart = [];
          state.paypalCheckoutToken = null;
          saveCart();
          window.location.assign(`/paypal/success?order_id=${encodeURIComponent(result.internal_order_id)}`);
        },
        onCancel() {
          window.location.assign("/paypal/cancel");
        },
        onError(error) {
          console.error("PayPal checkout error", error?.name || "Error");
          hint.textContent = "PayPal 付款未完成，訂單不會標記為已付款。";
          notify("PayPal 付款未完成，請稍後再試");
        },
      })
      .render("#paypal-button-container");
  } catch (error) {
    container.innerHTML = "";
    hint.textContent = error.message || "PayPal 國際付款目前無法使用。";
  }
}

async function loadOrders() {
  const wrap = $("#ordersList");
  if (!wrap) return;
  try {
    const data = await api("/api/orders");
    const orders = data.orders || [];
    wrap.innerHTML = orders.length
      ? orders
          .map(
            (order) => `
              <div class="panel order-card">
                <strong>訂單 #${order.id}</strong>
                <div class="line">
                  <span class="tag">訂購人：${escapeHtml(order.customer_name || order.username || "")}</span>
                  <span class="tag">審核：${escapeHtml(orderReviewLabel(order.review_status))}</span>
                  <span class="tag">狀態：${escapeHtml(order.status || "")}</span>
                </div>
                <div class="hint">${money(order.total)}</div>
              </div>
            `
          )
          .join("")
      : `<p class="hint">目前沒有訂單。</p>`;
  } catch (error) {
    wrap.innerHTML = `<p class="hint">${escapeHtml(error.message)}</p>`;
  }
}

async function loadAdmin() {
  const usersWrap = $("#usersTable");
  const ordersWrap = $("#adminOrders");
  if (!usersWrap || !ordersWrap) return;

  try {
    const [usersRes, ordersRes] = await Promise.all([api("/api/users"), api("/api/orders")]);
    const users = usersRes.users || [];
    const orders = ordersRes.orders || [];
    const ordersByUser = new Map();
    orders.forEach((order) => {
      if (!ordersByUser.has(order.user_id)) ordersByUser.set(order.user_id, []);
      ordersByUser.get(order.user_id).push(order);
    });

    usersWrap.innerHTML = users.length
      ? users
          .map((user) => {
            const isCurrentAdmin = state.user && state.user.id === user.id;
            const userOrders = ordersByUser.get(user.id) || [];
            const hasPendingOrders = userOrders.some((order) => order.review_status === "pending");
            const statusLabel =
              user.status === "approved"
                ? "已通過"
                : user.status === "rejected"
                  ? "已拒絕"
                  : "待審核";
            const canReview = user.status !== "approved";
            const canDeleteMember = !isCurrentAdmin && !hasPendingOrders;
            const role = escapeHtml(user.role || "member");
            return `
              <div class="table-row">
                <div class="line">
                  <strong>${escapeHtml(user.username)}</strong>
                  <span class="tag">${role}</span>
                </div>
                <div class="line">
                  <span>${escapeHtml(user.email || "")}</span>
                  <span class="tag">${escapeHtml(statusLabel)}</span>
                </div>
                <div class="table-actions">
                  ${isCurrentAdmin ? `<span class="tag">目前登入中</span>` : ""}
                  ${
                    isCurrentAdmin
                      ? ""
                      : canReview
                        ? `<button type="button" class="primary" onclick="reviewUser(${user.id}, 'approved', '${role}')">通過審核</button>
                           <button type="button" onclick="reviewUser(${user.id}, 'rejected', '${role}')">拒絕</button>`
                        : `<button type="button" onclick="reviewUser(${user.id}, 'pending', '${role}')">改回待審核</button>`
                  }
                  <button type="button" class="danger" ${canDeleteMember ? "" : "disabled"} onclick="deleteMember(${user.id})">刪除會員資料</button>
                </div>
              </div>
            `;
          })
          .join("")
      : `<p class="hint">目前沒有會員資料。</p>`;

    ordersWrap.innerHTML = orders.length
      ? orders
          .map(
            (order) => `
              <div class="table-row">
                <div class="line">
                  <strong>#${order.id}</strong>
                  <span>${money(order.total)}</span>
                </div>
                <div class="line">
                  <span class="tag">訂購人：${escapeHtml(order.customer_name || order.username || "")}</span>
                  <span class="tag">審核：${escapeHtml(orderReviewLabel(order.review_status))}</span>
                  <span class="tag">狀態：${escapeHtml(order.status || "")}</span>
                </div>
                <div class="line">
                  <span>聯絡電話：${escapeHtml(order.phone || "未提供")}</span>
                  <span>地址：${escapeHtml(order.address || "未提供")}</span>
                </div>
                <div class="hint">備註：${escapeHtml(order.note || "無")}</div>
                <div class="table-actions">
                  <button type="button" class="primary" onclick="reviewOrder(${order.id}, 'approved')">通過審核</button>
                  <button type="button" onclick="reviewOrder(${order.id}, 'rejected')">拒絕</button>
                  <button type="button" onclick="reviewOrder(${order.id}, 'pending')">改回待審核</button>
                  <button type="button" class="danger" ${order.review_status === "pending" ? "disabled" : ""} onclick="deleteOrder(${order.id})">刪除訂單</button>
                </div>
              </div>
            `
          )
          .join("")
      : `<p class="hint">目前沒有訂單。</p>`;
  } catch (error) {
    usersWrap.innerHTML = `<p class="hint">${escapeHtml(error.message)}</p>`;
    ordersWrap.innerHTML = `<p class="hint">${escapeHtml(error.message)}</p>`;
  }
}

async function reviewOrder(orderId, reviewStatus) {
  try {
    await api(`/api/orders/${orderId}`, {
      method: "PUT",
      body: JSON.stringify({ review_status: reviewStatus }),
    });
    await loadAdmin();
    notify("訂單審核已更新");
  } catch (error) {
    notify(error.message);
  }
}

async function reviewUser(userId, status, role = "member") {
  try {
    await api(`/api/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify({ status, role }),
    });
    await loadAdmin();
    notify("會員審核已更新");
  } catch (error) {
    notify(error.message);
  }
}

async function deleteOrder(orderId) {
  if (!confirm("確定要刪除這筆已審核訂單嗎？")) return;
  try {
    await api(`/api/orders/${orderId}`, { method: "DELETE" });
    await loadAdmin();
    notify("訂單資料已刪除");
  } catch (error) {
    notify(error.message);
  }
}

async function deleteMember(userId) {
  if (!confirm("確定要刪除這位會員資料嗎？若沒有待審核訂單，系統會一併移除其已審核訂單。")) return;
  try {
    await api(`/api/users/${userId}`, { method: "DELETE" });
    await loadAdmin();
    notify("會員資料已刪除");
  } catch (error) {
    notify(error.message);
  }
}

function bindEvents() {
  $$("[data-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });

  $$("[data-read-mode]").forEach((button) => {
    button.addEventListener("click", () => setReadMode(button.dataset.readMode));
  });

  const openCartBtn = $("#openCartBtn");
  const closeCartBtn = $("#closeCartBtn");
  const cartDrawer = $("#cartDrawer");
  if (openCartBtn && cartDrawer) {
    openCartBtn.addEventListener("click", () => cartDrawer.classList.add("open"));
  }
  if (closeCartBtn && cartDrawer) {
    closeCartBtn.addEventListener("click", () => cartDrawer.classList.remove("open"));
  }

  const productDetail = $("#productDetail");
  if (productDetail) {
    productDetail.addEventListener("click", (event) => {
      if (event.target === productDetail) closeProductDetail();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && productDetail.classList.contains("open")) closeProductDetail();
    });
  }

  const checkoutForm = $("#checkoutForm");
  if (checkoutForm) checkoutForm.addEventListener("submit", checkout);
  const ecpayCheckoutBtn = $("#ecpayCheckoutBtn");
  if (ecpayCheckoutBtn) ecpayCheckoutBtn.addEventListener("click", checkoutWithEcpay);

  const logoutBtn = $("#logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      try {
        await api("/api/logout", { method: "POST" });
      } catch {}
      state.user = null;
      state.csrfToken = null;
      syncChrome();
      showView("shop");
    });
  }

  const loginForm = $("#loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const data = Object.fromEntries(new FormData(event.currentTarget));
        const res = await api("/api/login", { method: "POST", body: JSON.stringify(data) });
        state.user = res.user;
        state.csrfToken = res.csrf_token || null;
        syncChrome();
        showView("shop");
        notify("登入成功");
      } catch (error) {
        notify(error.message);
      }
    });
  }

}

async function init() {
  bindEvents();

  try {
    await loadMe();
  } catch {
    state.user = null;
    syncChrome();
  }

  try {
    await loadProducts();
  } catch (error) {
    const grid = $("#readContent");
    if (grid) grid.innerHTML = `<p class="hint">${escapeHtml(error.message)}</p>`;
  }
  renderReadContent();

  try {
    await loadVisitStats();
  } catch {
    renderVisitStats();
  }

  renderCart();
  initPayPal();
}

window.addToCart = addToCart;
window.changeQty = changeQty;
window.removeFromCart = removeFromCart;
window.openPreview = openPreview;

init().catch((error) => notify(error.message));


