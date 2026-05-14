const state = {
  user: null,
  products: [],
  cart: loadCart(),
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const DEFAULT_PRODUCT_IMAGE = window.DEFAULT_PRODUCT_IMAGE || "/static/vios.png";

const USER_STATUS_LABELS = {
  pending: "敺祟??,
  approved: "撌脫??,
  rejected: "撌脫?蝯?,
};

const ROLE_LABELS = {
  member: "?",
  admin: "蝞∠???,
};

const ORDER_STATUS_LABELS = {
  new: "?啗???,
  paid: "撌脖?甈?,
  processing: "??銝?,
  shipped: "撌脣鞎?,
  completed: "撌脣???,
  cancelled: "撌脣?瘨?,
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
  if (!data.ok) throw new Error(data.error || "?潛??芷????航炊");
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
  return USER_STATUS_LABELS[status] || status || "?芰";
}

function translateRole(role) {
  return ROLE_LABELS[role] || role || "?芰";
}

function translateOrderStatus(status) {
  return ORDER_STATUS_LABELS[status] || status || "?芰";
}

function getHeroStatus(user) {
  if (!user) return "?餃敺銝";
  if (user.status === "approved") return "?典歇??撖拇嚗隞乩???;
  if (user.status === "pending") return "撣唾?撖拇銝哨???敺?臭???;
  if (user.status === "rejected") return "撣唾?撌脰◤??嚗??舐窗蝞∠???;
  return "撣唾???撣?;
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
    ? `${state.user.username}嚚?{translateUserStatus(state.user.status)}嚚?{translateRole(state.user.role)}`
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
      const image = product.image_url || DEFAULT_PRODUCT_IMAGE;
      const disabled = product.stock <= 0 ? "disabled" : "";
      const buttonText = product.stock <= 0 ? "撌脣摰? : "?鞈潛頠?;
      return `
        <article class="product-card">
          <img src="${escapeHtml(image)}" alt="${escapeHtml(product.name)}">
          <div class="product-body">
            <div class="product-meta">
              <span class="tag">${escapeHtml(product.category)}</span>
              <span class="price">${money(product.price)}</span>
            </div>
            <h3>${escapeHtml(product.name)}</h3>
            <p>${escapeHtml(product.description || "?怎???膩")}</p>
            <div class="line">
              <small>摨怠? ${product.stock}</small>
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
  notify("撌脣??亥頃?抵?");
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
    wrap.innerHTML = `<p class="hint">鞈潛頠??????/p>`;
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
              <button type="button" class="ghost" onclick="removeFromCart(${product.id})">蝘駁</button>
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
    notify("隢??餃銝阡?撖拇敺?銝");
    return;
  }
  if (state.user.status !== "approved") {
    notify("?桀?撣唾?撠??撖拇嚗?瘜???);
    return;
  }
  if (state.cart.length === 0) {
    notify("鞈潛頠蝛箇?");
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
    notify(`閮撌脤嚗楊??#${data.order_id}`);
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
              <strong>#${order.id}嚚?{escapeHtml(order.customer_name)}</strong>
              <span class="tag">${escapeHtml(translateOrderStatus(order.status))}</span>
            </div>
            <p class="hint">${escapeHtml(order.address)}嚚?{escapeHtml(order.phone)}</p>
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
    : `<p class="hint">?桀??????柴?/p>`;
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
        <small>${escapeHtml(user.email)}嚚?{escapeHtml(translateRole(user.role))}</small>
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
          <button onclick="saveUser(${user.id})">?脣?</button>
          <button class="danger" data-username="${escapeHtml(user.username)}" onclick="deleteUser(${user.id}, this.dataset.username)">?芷</button>
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
    notify("?鞈?撌脫??);
    loadAdmin();
  } catch (error) {
    notify(error.message);
  }
}

async function deleteUser(id, username) {
  if (!confirm(`蝣箏?閬?斗??～?{username}??嚗迨???⊥?敺拙??)) return;
  try {
    await api(`/api/users/${id}`, { method: "DELETE" });
    notify("?鞈?撌脣??);
    loadAdmin();
  } catch (error) {
    notify(error.message);
  }
}

async function updateOrder(id, status) {
  try {
    await api(`/api/orders/${id}`, { method: "PUT", body: JSON.stringify({ status }) });
    notify("閮??歇?湔");
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
      notify("?餃??");
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
      notify(res.message || "?唾???");
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



