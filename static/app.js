const state = {
  user: null,
  products: [],
  cart: loadCart(),
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const USER_STATUS_LABELS = {
  pending: "待審核",
  approved: "已核准",
  rejected: "已拒絕",
};

const ROLE_LABELS = {
  member: "會員",
  admin: "管理員",
};

const ORDER_STATUS_LABELS = {
  new: "新訂單",
  paid: "已付款",
  processing: "處理中",
  shipped: "已出貨",
  completed: "已完成",
  cancelled: "已取消",
};

function loadCart() {
  try {
    const raw = localStorage.getItem("studio_cart");
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function money(value) {
  return `NT$${Number(value || 0).toLocaleString("zh-TW")}`;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "發生未預期的錯誤");
  return data;
}

function notify(message) {
  const box = $("#notice");
  box.textContent = message;
  box.classList.remove("hidden");
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => box.classList.add("hidden"), 3600);
}

function translateUserStatus(status) {
  return USER_STATUS_LABELS[status] || status || "未知";
}

function translateRole(role) {
  return ROLE_LABELS[role] || role || "未知";
}

function translateOrderStatus(status) {
  return ORDER_STATUS_LABELS[status] || status || "未知";
}

function getHeroStatus(user) {
  if (!user) return "登入後可下單";
  if (user.status === "approved") return "您已通過審核，可以下單";
  if (user.status === "pending") return "帳號審核中，通過後即可下單";
  if (user.status === "rejected") return "帳號已被拒絕，請聯絡管理員";
  return "帳號狀態異常";
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

  $("#userBadge").textContent = state.user
    ? `${state.user.username}｜${translateUserStatus(state.user.status)}｜${translateRole(state.user.role)}`
    : "";
  $("#heroStatus").textContent = getHeroStatus(state.user);
}

async function loadMe() {
  const data = await api("/api/me");
  state.user = data.user;
  syncChrome();
}

async function loadProducts(admin = false) {
  const data = await api(`/api/products${admin ? "?admin=1" : ""}`);
  if (!admin) {
    state.products = data.products;
    renderProducts();
  }
  return data.products;
}

function renderProducts() {
  const grid = $("#productsGrid");
  grid.innerHTML = state.products
    .map((product) => {
      const image = product.image_url || "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=900&q=80";
      const disabled = product.stock <= 0 ? "disabled" : "";
      const buttonText = product.stock <= 0 ? "已售完" : "加入購物車";
      return `
        <article class="product-card">
          <img src="${escapeHtml(image)}" alt="${escapeHtml(product.name)}">
          <div class="product-body">
            <div class="product-meta">
              <span class="tag">${escapeHtml(product.category)}</span>
              <span class="price">${money(product.price)}</span>
            </div>
            <h3>${escapeHtml(product.name)}</h3>
            <p>${escapeHtml(product.description || "暫無商品描述")}</p>
            <div class="line">
              <small>庫存 ${product.stock}</small>
              <button class="primary" ${disabled} onclick="addToCart(${product.id})">${buttonText}</button>
            </div>
          </div>
        </article>
      `;
    })
    .join("");
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

function saveCart() {
  localStorage.setItem("studio_cart", JSON.stringify(state.cart));
  renderCart();
}

function renderCart() {
  $("#cartCount").textContent = state.cart.reduce((sum, item) => sum + item.quantity, 0);
  const wrap = $("#cartItems");
  let total = 0;

  if (state.cart.length === 0) {
    wrap.innerHTML = `<p class="hint">購物車目前沒有商品。</p>`;
  } else {
    wrap.innerHTML = state.cart
      .map((item) => {
        const product = state.products.find((p) => p.id === item.product_id);
        if (!product) return "";
        const subtotal = product.price * item.quantity;
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

  $("#cartTotal").textContent = money(total);
}

function changeQty(productId, delta) {
  const item = state.cart.find((entry) => entry.product_id === productId);
  if (!item) return;
  item.quantity += delta;
  if (item.quantity <= 0) removeFromCart(productId);
  else saveCart();
}

function removeFromCart(productId) {
  state.cart = state.cart.filter((entry) => entry.product_id !== productId);
  saveCart();
}

async function checkout(event) {
  event.preventDefault();

  if (!state.user) {
    notify("請先登入並通過審核後再下單");
    return;
  }
  if (state.user.status !== "approved") {
    notify("目前帳號尚未通過審核，暫時無法下單");
    return;
  }
  if (state.cart.length === 0) {
    notify("購物車是空的");
    return;
  }

  const form = event.currentTarget;
  const payload = Object.fromEntries(new FormData(form));
  payload.items = state.cart;

  try {
    const data = await api("/api/orders", { method: "POST", body: JSON.stringify(payload) });
    state.cart = [];
    saveCart();
    form.reset();
    $("#cartDrawer").classList.remove("open");
    await loadProducts();
    notify(`訂單已送出，編號：#${data.order_id}`);
  } catch (error) {
    notify(error.message);
  }
}

async function loadOrders() {
  try {
    const data = await api("/api/orders");
    renderOrders(data.orders, $("#ordersList"), false);
  } catch (error) {
    $("#ordersList").innerHTML = `<p class="hint">${escapeHtml(error.message)}</p>`;
  }
}

function renderOrders(orders, target, admin) {
  target.innerHTML = orders.length
    ? orders
        .map((order) => `
          <article class="order-card panel">
            <div class="line">
              <strong>#${order.id}｜${escapeHtml(order.customer_name)}</strong>
              <span class="tag">${escapeHtml(translateOrderStatus(order.status))}</span>
            </div>
            <p class="hint">${escapeHtml(order.address)}｜${escapeHtml(order.phone)}</p>
            <div>
              ${order.items
                .map(
                  (item) => `<div class="line"><span>${escapeHtml(item.product_name)} x ${item.quantity}</span><strong>${money(item.subtotal)}</strong></div>`,
                )
                .join("")}
            </div>
            <div class="line"><span>${escapeHtml(order.created_at)}</span><strong>${money(order.total)}</strong></div>
            ${admin ? orderStatusControl(order) : ""}
          </article>
        `)
        .join("")
    : `<p class="hint">目前還沒有訂單。</p>`;
}

function orderStatusControl(order) {
  const statuses = ["new", "paid", "processing", "shipped", "completed", "cancelled"];
  return `
    <div class="table-actions">
      <select onchange="updateOrder(${order.id}, this.value)">
        ${statuses
          .map((status) => `<option value="${status}" ${status === order.status ? "selected" : ""}>${translateOrderStatus(status)}</option>`)
          .join("")}
      </select>
    </div>
  `;
}

async function loadAdmin() {
  try {
    const [users, orders] = await Promise.all([
      api("/api/users"),
      api("/api/orders"),
    ]);
    renderUsers(users.users);
    renderOrders(orders.orders, $("#adminOrders"), true);
  } catch (error) {
    notify(error.message);
  }
}

function renderUsers(users) {
  $("#usersTable").innerHTML = users
    .map((user) => `
      <div class="table-row">
        <div class="line">
          <strong>${escapeHtml(user.username)}</strong>
          <span class="tag">${escapeHtml(translateUserStatus(user.status))}</span>
        </div>
        <small>${escapeHtml(user.email)}｜${escapeHtml(translateRole(user.role))}</small>
        <div class="table-actions">
          <select id="status-${user.id}">
            ${["pending", "approved", "rejected"]
              .map((status) => `<option value="${status}" ${status === user.status ? "selected" : ""}>${translateUserStatus(status)}</option>`)
              .join("")}
          </select>
          <select id="role-${user.id}">
            ${["member", "admin"]
              .map((role) => `<option value="${role}" ${role === user.role ? "selected" : ""}>${translateRole(role)}</option>`)
              .join("")}
          </select>
          <button onclick="saveUser(${user.id})">儲存</button>
          <button class="danger" data-username="${escapeHtml(user.username)}" onclick="deleteUser(${user.id}, this.dataset.username)">刪除</button>
        </div>
      </div>
    `)
    .join("");
}

async function saveUser(id) {
  try {
    await api(`/api/users/${id}`, {
      method: "PUT",
      body: JSON.stringify({
        status: $(`#status-${id}`).value,
        role: $(`#role-${id}`).value,
      }),
    });
    notify("會員資料已更新");
    loadAdmin();
  } catch (error) {
    notify(error.message);
  }
}

async function deleteUser(id, username) {
  if (!confirm(`確定要刪除會員「${username}」嗎？此操作無法復原。`)) return;
  try {
    await api(`/api/users/${id}`, { method: "DELETE" });
    notify("會員資料已刪除");
    loadAdmin();
  } catch (error) {
    notify(error.message);
  }
}

async function updateOrder(id, status) {
  try {
    await api(`/api/orders/${id}`, { method: "PUT", body: JSON.stringify({ status }) });
    notify("訂單狀態已更新");
    loadAdmin();
  } catch (error) {
    notify(error.message);
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function bindEvents() {
  $$("[data-view]").forEach((button) => button.addEventListener("click", () => showView(button.dataset.view)));
  $("#openCartBtn").addEventListener("click", () => $("#cartDrawer").classList.add("open"));
  $("#closeCartBtn").addEventListener("click", () => $("#cartDrawer").classList.remove("open"));
  $("#checkoutForm").addEventListener("submit", checkout);
  $("#logoutBtn").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST" });
    state.user = null;
    syncChrome();
    showView("shop");
  });
  $("#loginForm").addEventListener("submit", async (event) => {
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
  $("#registerForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const data = Object.fromEntries(new FormData(form));
      const res = await api("/api/register", { method: "POST", body: JSON.stringify(data) });
      form.reset();
      notify(res.message || "申請成功");
    } catch (error) {
      notify(error.message);
    }
  });
}

async function init() {
  bindEvents();
  await loadMe();
  await loadProducts();
  renderCart();
}

init().catch((error) => notify(error.message));
