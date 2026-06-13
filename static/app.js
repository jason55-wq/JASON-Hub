const state = {
  user: null,
  products: [],
  cart: loadCart(),
  visitorCount: 0,
  readMode: "project",
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

async function api(path, options = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
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
        ? "會員已通過審核"
        : "會員待審核"
      : "登入後可下單";
  }
}

async function loadMe() {
  const data = await api("/api/me");
  state.user = data.user;
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
  `;

  wrap.innerHTML = state.readMode === "product" ? "" : projectContent;
}

function addToCart(productId) {
  const product = state.products.find((item) => item.id === productId);
  if (!product || product.stock <= 0) return;
  const found = state.cart.find((item) => item.product_id === productId);
  if (found) found.quantity += 1;
  else state.cart.push({ product_id: productId, quantity: 1 });
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

  if (!state.user) {
    notify("請先登入");
    return;
  }
  if (state.user.status !== "approved") {
    notify("會員尚未通過審核");
    return;
  }
  if (!state.cart.length) {
    notify("請先加入商品");
    return;
  }

  const form = new FormData(checkoutForm);
  const payload = {
    items: state.cart,
    customer_name: String(form.get("customer_name") || "").trim(),
    phone: String(form.get("phone") || "").trim(),
    address: String(form.get("address") || "").trim(),
    note: String(form.get("note") || "").trim(),
  };

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
                  <span class="tag">審核：${escapeHtml(orderReviewLabel(order.review_status))}</span>
                  <span class="tag">狀態：${escapeHtml(order.status || "")}</span>
                </div>
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

  const checkoutForm = $("#checkoutForm");
  if (checkoutForm) checkoutForm.addEventListener("submit", checkout);

  const logoutBtn = $("#logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      try {
        await api("/api/logout", { method: "POST" });
      } catch {}
      state.user = null;
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
        syncChrome();
        showView("shop");
        notify("登入成功");
      } catch (error) {
        notify(error.message);
      }
    });
  }

  const registerForm = $("#registerForm");
  if (registerForm) {
    registerForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      try {
        const data = Object.fromEntries(new FormData(form));
        const res = await api("/api/register", { method: "POST", body: JSON.stringify(data) });
        form.reset();
        notify(res.message || "註冊成功");
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
}

window.addToCart = addToCart;
window.changeQty = changeQty;
window.removeFromCart = removeFromCart;

init().catch((error) => notify(error.message));


