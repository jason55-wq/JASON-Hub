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
  if (state.readMode === "project" && window.location.pathname === "/") {
    window.history.replaceState({}, "", "/articles");
  } else if (state.readMode === "product" && window.location.pathname.startsWith("/articles")) {
    window.history.replaceState({}, "", "/");
  }
  renderReadContent();
}

function formatPublishedDate(value) {
  const [year, month, day] = String(value).split("-");
  return `${year}年${month}月${day}日`;
}

function articleRoute() {
  const parts = decodeURIComponent(window.location.pathname)
    .split("/")
    .filter(Boolean);
  if (parts[0] !== "articles") return { type: "all" };
  if (parts.length === 1) return { type: "all" };
  if (/^\d{4}$/.test(parts[1]) && parts.length === 2) {
    return { type: "year", year: parts[1] };
  }
  if (/^\d{4}$/.test(parts[1]) && /^\d{2}$/.test(parts[2] || "") && parts.length === 3) {
    return { type: "month", year: parts[1], month: parts[2] };
  }
  if (parts.length === 2) return { type: "article", slug: parts[1] };
  return { type: "not-found" };
}

function parseArticles(projectContent) {
  const template = document.createElement("template");
  template.innerHTML = projectContent;
  return [...template.content.querySelectorAll("article[data-article-slug]")]
    .map((element) => ({
      slug: element.dataset.articleSlug,
      publishedDate: element.dataset.publishedDate,
      title: element.querySelector("h3")?.textContent.trim() || "文章",
      element,
    }))
    .sort((a, b) => b.publishedDate.localeCompare(a.publishedDate));
}

function renderArticleArchive(articles) {
  const archive = new Map();
  articles.forEach((article) => {
    const [year, month] = article.publishedDate.split("-");
    if (!archive.has(year)) archive.set(year, new Set());
    archive.get(year).add(month);
  });
  return [...archive.entries()]
    .sort(([a], [b]) => b.localeCompare(a))
    .map(
      ([year, months]) => `
        <div class="article-archive-year">
          <a href="/articles/${year}" data-article-link>${year} 年</a>
          <ul>
            ${[...months]
              .sort((a, b) => b.localeCompare(a))
              .map((month) => `<li><a href="/articles/${year}/${month}" data-article-link>${month} 月</a></li>`)
              .join("")}
          </ul>
        </div>`
    )
    .join("");
}

function renderArticles(projectContent) {
  const allArticles = parseArticles(projectContent);
  const route = articleRoute();
  let articles = allArticles;
  let heading = "全部文章";

  if (route.type === "year") {
    articles = allArticles.filter((article) => article.publishedDate.startsWith(`${route.year}-`));
    heading = `${route.year} 年文章`;
  } else if (route.type === "month") {
    articles = allArticles.filter((article) => article.publishedDate.startsWith(`${route.year}-${route.month}-`));
    heading = `${route.year} 年 ${route.month} 月文章`;
  } else if (route.type === "article") {
    articles = allArticles.filter((article) => article.slug === route.slug);
    heading = articles[0]?.title || "找不到文章";
  } else if (route.type === "not-found") {
    articles = [];
    heading = "找不到文章";
  }

  const isSingle = route.type === "article" && articles.length === 1;
  const articleHtml = articles.length
    ? articles
        .map((article) => {
          const card = article.element.cloneNode(true);
          const title = card.querySelector("h3");
          const date = document.createElement("p");
          date.className = "article-published-date";
          date.textContent = `發布日期：${formatPublishedDate(article.publishedDate)}`;
          title?.insertAdjacentElement("afterend", date);
          if (!isSingle) {
            const link = document.createElement("a");
            link.className = "article-permalink";
            link.href = `/articles/${article.slug}`;
            link.dataset.articleLink = "";
            link.textContent = "閱讀單篇文章";
            date.insertAdjacentElement("afterend", link);
          }
          return card.outerHTML;
        })
        .join("")
    : `<div class="panel"><p class="hint">這個分類目前沒有文章。</p><a href="/articles" data-article-link>返回全部文章</a></div>`;

  return `
    <div class="article-layout">
      <details class="article-archive" open>
        <summary>文章分類</summary>
        <a class="article-archive-all" href="/articles" data-article-link>全部文章</a>
        ${renderArticleArchive(allArticles)}
      </details>
      <section class="article-results" aria-labelledby="articleArchiveTitle">
        <h2 id="articleArchiveTitle" class="article-results-title">${escapeHtml(heading)}</h2>
        ${articleHtml}
      </section>
    </div>`;
}

function renderReadContent() {
  const wrap = $("#readContent");
  if (!wrap) return;

  $$(".mode-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.readMode === state.readMode);
  });

  const projectContent = `
    <article class="story-card story-card-project" data-article-slug="ai-assisted-embedded-debugging" data-published-date="2026-08-28">
      <div class="story-body">
        <div class="story-head">
          <span class="tag">AI Debug</span>
          <span class="tag">嵌入式系統</span>
          <span class="tag">軟硬體整合</span>
        </div>
        <h3>使用 AI 工具進行 Debug：軟硬體整合專案實作心得</h3>

        <p>近期在進行嵌入式系統與軟硬體整合專案時，我開始嘗試將 <strong>AI 工具加入 Debug 與開發流程</strong>。經過實際使用後，我發現 AI 最大的價值並不是直接幫我完成所有程式，而是協助分析問題、閱讀錯誤訊息、提供排查方向，再由我透過實際硬體測試驗證結果。</p>

        <h4>從「寫程式」到「找問題」</h4>
        <p>軟硬體整合專案與單純撰寫電腦程式有很大的不同。</p>
        <p>當程式無法正常執行時，問題不一定出現在 Code，也可能來自 MCU 設定、腳位配置、時脈、通訊參數、接線、電源或硬體本身。</p>
        <p>例如 UART、I2C、SPI 等通訊功能發生異常時，如果只是不斷修改程式碼，很容易花費大量時間卻找不到真正原因。</p>
        <p>因此，我開始嘗試把問題、程式碼、錯誤訊息以及實際測試結果提供給 AI，請 AI 協助分析可能的原因，再依照建議逐項進行測試。</p>

        <h4>AI 成為我的 Debug 輔助工具</h4>
        <p>實際使用後，我認為 AI 很適合協助整理 Debug 思路。</p>
        <p>例如遇到 UART 無法正常收發資料，可以先整理目前使用的 MCU、系統時脈、Baud Rate、Timer 設定、TX/RX 接線以及程式碼，再讓 AI 分析可能存在的問題。</p>
        <p>AI 可以快速提出幾個需要檢查的方向，但真正重要的是接下來的「驗證」。</p>
        <p>我會根據建議重新確認 Datasheet、修改參數、重新編譯與燒錄，再透過電腦、USB-UART 或其他測試工具觀察實際結果。</p>
        <p>因此整個流程逐漸變成：</p>
        <p><strong>發現問題 → 整理現象 → 詢問 AI → 分析可能原因 → 修改程式或設定 → 燒錄測試 → 驗證結果 → 繼續縮小問題範圍</strong></p>
        <p>這種方式讓 Debug 不再只是漫無目的地修改 Code，而是更有系統地排除問題。</p>

        <h4>AI 不能取代實際硬體測試</h4>
        <p>這也是我在實作過程中認為非常重要的一點。</p>
        <p>AI 可以閱讀程式碼，也能根據提供的資訊推測問題，但 AI 並沒有直接看到我手上的電路板。</p>
        <p>實際的晶振頻率是否正確、TX/RX 是否接反、電壓是否正常、MCU 是否成功燒錄、通訊資料是否真的送出，最後仍然需要透過實際測試確認。</p>
        <p>有時候程式看起來完全正確，真正的問題卻可能只是硬體設定與程式假設不同。</p>
        <p>這也讓我逐漸建立一個觀念：</p>
        <p><strong>AI 提供的是 Debug 方向，而實際測試提供的才是工程證據。</strong></p>

        <h4>學習效率上的改變</h4>
        <p>以前遇到不熟悉的錯誤時，可能需要搜尋大量文章、論壇與 Datasheet，才能找到可能相關的資訊。</p>
        <p>現在透過 AI，可以先快速了解錯誤訊息代表什麼，再知道應該搜尋 Datasheet 的哪個章節，以及哪些參數最值得優先檢查。</p>
        <p>這對學習新的 MCU 或通訊協定非常有幫助。</p>
        <p>不過，我也發現不能只把錯誤訊息貼給 AI，然後直接複製產生的程式。</p>
        <p>更有效的方法是了解 AI 為什麼建議修改這個地方，再透過實際測試確認修改是否有效。</p>
        <p>如此一來，每解決一次問題，就不只是「把 Bug 修掉」，而是多理解一個技術觀念。</p>

        <h4>從 AI 使用者轉變成問題分析者</h4>
        <p>透過這些實作經驗，我認為使用 AI 開發程式最重要的能力之一，反而是「如何描述問題」。</p>
        <p>如果只告訴 AI「程式不能動」，能得到的資訊非常有限。</p>
        <p>但如果能清楚提供：</p>
        <p><strong>MCU 型號、系統時脈、開發環境、編譯器、通訊參數、接線方式、錯誤訊息、程式碼以及實際測試結果</strong></p>
        <p>AI 就更容易協助分析可能原因。</p>
        <p>這個過程其實也在訓練自己的工程思考能力，因為要讓別人理解問題，自己必須先整理目前知道的資訊。</p>

        <h4>專案心得</h4>
        <p>經過這段時間的實作，我對 AI 輔助嵌入式系統開發的看法也有所改變。</p>
        <p>AI 不只是「產生 Code 的工具」，它更適合作為一個協助閱讀程式、分析錯誤、整理文件與建立 Debug 思路的工程輔助工具。</p>
        <p>真正的軟硬體整合仍然需要自己進行接線、編譯、燒錄、量測、測試與驗證。</p>
        <p>我認為最有效率的開發方式不是「AI 幫我寫完」，而是：</p>
        <p><strong>我負責定義問題與驗證結果，AI 協助分析與提供方向。</strong></p>
        <p>透過這種合作方式，可以提升 Debug 效率，同時保留實際動手與理解原理的學習過程。</p>
        <p>對我而言，每一次成功解決 Bug，都不只是讓程式重新運作，而是累積一次真正的軟硬體整合經驗。</p>
        <p>未來我也希望持續將 AI 工具應用在嵌入式系統、韌體開發與軟硬體整合專案中，並建立自己的 Debug 流程與技術紀錄，讓 AI 成為提升工程開發效率的工具，而不是取代工程判斷的工具。</p>
      </div>
    </article>
    <article class="story-card story-card-project" data-article-slug="personal-ai-knowledge-base" data-published-date="2026-08-28">
      <div class="story-body">
        <div class="story-head">
          <span class="tag">個人 AI 知識庫</span>
          <span class="tag">RAG</span>
          <span class="tag">GPT</span>
        </div>
        <h3>Jason 個人 AI 知識庫</h3>
        <p><strong>地端 RAG 文件檢索與 GPT 問答系統</strong></p>

        <h4>專案介紹</h4>
        <p><strong>Jason 個人 AI 知識庫</strong>是一套以「個人資料管理」為核心所開發的 AI 知識管理系統，結合地端文件儲存、RAG（Retrieval-Augmented Generation，檢索增強生成）技術與 GPT，讓使用者可以建立屬於自己的私人 AI 資料庫。</p>
        <p>不同於一般 AI 問答系統主要依賴模型既有知識，本系統的核心概念是讓 AI 優先根據使用者自行建立與上傳的資料進行檢索，再將相關內容提供給 GPT 進行整理與回答，使 AI 能夠針對個人文件提供更具依據的問答結果。</p>

        <h4>專案功能</h4>
        <p>系統支援將不同類型的個人資料集中管理，並透過文件解析、文字切割、向量化與語意搜尋建立 RAG 檢索流程。當使用者提出問題時，系統會先從個人知識庫中搜尋最相關的內容，再將檢索結果交由 GPT 產生回答。</p>
        <p>主要功能包含：</p>
        <ul>
          <li>建立多個個人知識庫與資料分類</li>
          <li>上傳與管理 PDF、Word、PPT、TXT 等文件</li>
          <li>自動解析與整理文件內容</li>
          <li>建立文件向量索引</li>
          <li>使用 RAG 技術進行語意檢索</li>
          <li>串接 GPT 進行自然語言問答</li>
          <li>根據個人資料產生具有上下文的回答</li>
          <li>顯示回答所參考的文件來源</li>
          <li>管理、搜尋與刪除已上傳資料</li>
          <li>將不同領域資料建立成獨立知識庫</li>
        </ul>

        <h4>系統概念</h4>
        <p>整體資料處理流程為：</p>
        <p><strong>文件上傳 → 文件解析 → 文字切割 → Embedding 向量化 → 向量資料庫 → RAG 語意檢索 → GPT → 回答與資料來源</strong></p>
        <p>透過這套架構，可以讓大型語言模型不只是依靠自身訓練資料回答問題，而是結合使用者建立的個人資料庫，形成更符合個人需求的 AI 助理。</p>

        <h4>開發目的</h4>
        <p>隨著個人累積的 PDF、課程講義、研究資料、技術文件與筆記越來越多，傳統透過資料夾逐一尋找文件的方式效率有限。</p>
        <p>因此，我希望建立一套屬於自己的 AI 知識管理平台。</p>
        <p>例如將「嵌入式系統」、「程式設計」、「研究資料」、「工作文件」等內容建立成不同知識庫，未來只需要透過自然語言提出問題，就能快速從大量個人文件中尋找相關資訊。</p>
        <p>這個專案不只是單純的 GPT 聊天介面，而是希望將 <strong>個人資料庫、RAG 與大型語言模型</strong>整合成一套真正能長期累積與使用的「個人 AI 第二大腦」。</p>

        <h4>專案特色</h4>
        <p>Jason 個人 AI 知識庫最大的特色，在於將<strong>資料掌控權與 AI 能力分開設計</strong>。</p>
        <p>文件與知識庫可以保留於自己的環境中，而 GPT 主要負責理解問題與整理檢索結果。未來系統也可以進一步加入地端大型語言模型，降低對單一雲端 AI 模型的依賴。</p>
        <p>因此，本系統具有良好的擴充性，未來可持續整合更多文件格式、Embedding 模型、向量資料庫與不同的大型語言模型。</p>

        <h4>未來規劃</h4>
        <p>後續預計持續加入多知識庫管理、進階搜尋、文件來源追蹤、對話紀錄、模型切換與權限管理等功能，並研究 GPT 與地端 LLM 混合使用的架構。</p>
        <p>最終目標是打造一套可以持續累積個人知識，並透過 AI 快速搜尋、理解與運用資料的：</p>
        <p><strong>Personal AI Knowledge Base — 個人 AI 知識庫。</strong></p>
      </div>
    </article>
    <article class="story-card story-card-project" data-article-slug="vios-voice-control" data-published-date="2026-06-13">
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
    <article class="story-card story-card-project" data-article-slug="ai-website-guide" data-published-date="2026-07-27">
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
    <article class="story-card story-card-project" data-article-slug="arduino-gbox-diy-review" data-published-date="2026-08-13">
      <div class="story-body">
        <div class="story-head">
          <span class="tag">Arduino GBOX DIY</span>
          <span class="tag">閱讀心得</span>
        </div>
        <h3>閱讀偉克多工作室 Arduino GBOX DIY 電子報心得</h3>

        <p>最近閱讀了偉克多工作室的《Arduino GBOX DIY –1 創刊號》，我覺得這份電子報和一般單純介紹 Arduino 程式語法的教材不太一樣，它更強調「實際動手做」以及將學到的技術慢慢累積成自己的工具箱。電子報一開始就提到，希望透過精簡閱讀，把更多時間留給實作，並鼓勵初學者從自己有興趣的主題開始探索。</p>

        <p>這一期讓我印象比較深刻的是 GBOX 的 DIY 實驗。內容從 WS2812 彩燈開始，介紹 5V、GND、DIN 與 Arduino UNO D7 的連接方式，接著加入喇叭、按鍵及音效控制，最後再整合成彩燈與「打怪」功能。後面的實驗更進一步利用兩個按鍵切換音效、彩燈以及打怪功能，讓原本單獨的硬體逐漸整合成一個完整作品。</p>

        <p>我認為這樣的學習方式對嵌入式系統初學者很有幫助。因為學 Arduino 或微控制器時，如果只有閱讀程式碼，很容易知道語法卻不知道如何實際應用。透過 LED、按鍵、喇叭等簡單元件開始，再逐漸增加功能，可以比較清楚地理解硬體與軟體之間的關係。</p>

        <p>電子報另外也介紹了剝線與銲接等基礎技巧，例如使用工具剝線、烙鐵上錫，以及將線材與接點先上錫後再進行焊接。第 7、8 頁更實際展示 USB 5V 延長配線以及 8051 自製電路板的配線方式。這讓我感受到，嵌入式系統並不只是寫程式，也包含配線、焊接、測試以及最後的整合。</p>

        <p>另一個我很有興趣的部分是電子報對 AI 程式設計的看法。內容提到使用 DeepSeek 產生程式後，仍然需要 RUN、找 BUG、DEBUG，最重要的是自己必須能夠看懂程式碼，才能真正完成測試；如果功能太複雜，也可以先更換版本或降低複雜程度。</p>

        <p>這點讓我很有共鳴。現在使用 AI 可以大幅降低寫程式的門檻，但是 AI 產生程式碼並不代表作品就完成了。真正重要的還是自己能不能理解程式的功能、實際燒錄到開發板、測試硬體，並在發生問題時知道如何一步一步排除。</p>

        <p>我也很認同電子報中「買回自己時間」的概念。將已經測試成功的程式與實驗整理成自己的資料庫，未來遇到類似的專案，就可以直接找出過去做過的功能，再修改與整合，而不需要每一次都重新開始。對我來說，這其實就是建立自己的嵌入式系統工具箱。</p>

        <p>電子報後段也讓我看到 GBOX 未來可以延伸的方向，包括 MP3、遙控、藍牙、中文語音以及聲控情境控制等功能。尤其聲控部分可以進一步發展成「聲控我的家」、聲控娛樂、查詢及其他程式設計應用。這讓我覺得，一個看似簡單的 Arduino 實驗，只要持續加入新的感測器、控制方式與程式功能，也可以慢慢發展成完整的嵌入式系統作品。</p>

        <p>閱讀完這一期電子報後，我最大的心得是：<strong>學習嵌入式系統不一定要一開始就挑戰非常困難的專案，反而可以從一個小功能開始，實際接線、寫程式、測試、DEBUG，再把成功的功能保存下來。</strong></p>

        <p>久而久之，LED、按鍵、聲音、遙控、藍牙、聲控等功能都會變成自己的技術工具。未來想製作新的作品時，就能將這些功能重新組合，從「照著做」慢慢進步到「自己設計」。</p>

        <p>我認為這也是偉克多工作室 GBOX DIY 電子報帶給我最大的啟發：<strong>學程式不是只為了把程式碼寫出來，而是透過一次又一次的實作，把知識真正變成自己可以運用的能力。</strong></p>
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

  wrap.innerHTML = renderArticles(projectContent);
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

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-article-link]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    window.history.pushState({}, "", link.href);
    state.readMode = "project";
    renderReadContent();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  window.addEventListener("popstate", () => {
    if (window.location.pathname.startsWith("/articles")) state.readMode = "project";
    renderReadContent();
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


