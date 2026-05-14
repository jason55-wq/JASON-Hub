const state = {
  user: null,
  products: [],
  cart: loadCart(),
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
    badge.textContent = state.user
      ? `${state.user.username} · ${state.user.status || ""} · ${state.user.role || ""}`
      : "";
  }
  const heroStatus = $("#heroStatus");
  if (heroStatus) {
    heroStatus.textContent = state.user
      ? state.user.status === "approved"
        ? "已登入並通過審核"
        : "已登入，等待審核"
      : "尚未登入";
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
    renderProducts();
  }
  return data.products || [];
}

function renderProducts() {
  const grid = $("#productsGrid");
  if (!grid) return;

  if (!state.products.length) {
    grid.innerHTML = `<p class="hint">目前沒有商品。</p>`;
    return;
  }

  grid.innerHTML = state.products
    .map((product) => {
      const image = product.image_url || DEFAULT_PRODUCT_IMAGE;
      const disabled = product.stock <= 0 ? "disabled" : "";
      const buttonText = product.stock <= 0 ? "售完" : "加入購物車";
      return `
        <article class="product-card">
          <img src="${escapeHtml(image)}" alt="${escapeHtml(product.name)}" onerror="this.src='${escapeHtml(DEFAULT_PRODUCT_IMAGE)}'">
          <div class="product-body">
            <div class="product-meta">
              <span class="tag">${escapeHtml(product.category || "商品")}</span>
              <span class="price">${money(product.price)}</span>
            </div>
            <h3>${escapeHtml(product.name)}</h3>
            <p>${escapeHtml(product.description || "商品介紹")}</p>
            <div class="line">
              <small>庫存 ${Number(product.stock || 0)}</small>
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
    wrap.innerHTML = `<p class="hint">購物車是空的。</p>`;
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
              <button type="button" class="ghost" onclick="removeFromCart(${product.id})">刪除</button>
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

  if (!state.user) {
    notify("請先登入");
    return;
  }
  if (state.user.status !== "approved") {
    notify("帳號尚未通過審核");
    return;
  }
  if (!state.cart.length) {
    notify("請先加入商品");
    return;
  }

  const form = new FormData(event.currentTarget);
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
    event.currentTarget.reset();
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
                <div class="hint">${escapeHtml(order.status || "")} · ${money(order.total)}</div>
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

    usersWrap.innerHTML = users.length
      ? users
          .map((user) => `<div class="table-row"><strong>${escapeHtml(user.username)}</strong><span>${escapeHtml(user.role || "")}</span></div>`)
          .join("")
      : `<p class="hint">沒有會員資料。</p>`;

    ordersWrap.innerHTML = orders.length
      ? orders
          .map((order) => `<div class="table-row"><strong>#${order.id}</strong><span>${money(order.total)}</span></div>`)
          .join("")
      : `<p class="hint">沒有訂單資料。</p>`;
  } catch (error) {
    usersWrap.innerHTML = `<p class="hint">${escapeHtml(error.message)}</p>`;
    ordersWrap.innerHTML = `<p class="hint">${escapeHtml(error.message)}</p>`;
  }
}

function bindEvents() {
  $$("[data-view]").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
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
      try {
        const data = Object.fromEntries(new FormData(event.currentTarget));
        const res = await api("/api/register", { method: "POST", body: JSON.stringify(data) });
        event.currentTarget.reset();
        notify(res.message || "申請成功");
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
    const grid = $("#productsGrid");
    if (grid) grid.innerHTML = `<p class="hint">${escapeHtml(error.message)}</p>`;
  }

  renderCart();
}

window.addToCart = addToCart;
window.changeQty = changeQty;
window.removeFromCart = removeFromCart;

init().catch((error) => notify(error.message));
