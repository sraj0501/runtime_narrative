(function () {
  "use strict";

  var NAV = window.NARRATIVE_NAV || [];
  var body = document.body;
  var currentPage = body.getAttribute("data-page") || "";

  /* ---------------- Theme ---------------- */
  function applyTheme(theme) {
    if (theme === "light" || theme === "dark") {
      document.documentElement.setAttribute("data-theme", theme);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
  }
  function currentTheme() {
    var stored = localStorage.getItem("rn-theme");
    if (stored) return stored;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  applyTheme(localStorage.getItem("rn-theme"));

  function initThemeToggle() {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      localStorage.setItem("rn-theme", next);
      applyTheme(next);
    });
  }

  /* ---------------- Mobile nav ---------------- */
  function initMobileNav() {
    var menuBtn = document.getElementById("menu-btn");
    var overlay = document.getElementById("sidebar-overlay");
    function close() { body.classList.remove("nav-open"); }
    if (menuBtn) menuBtn.addEventListener("click", function () { body.classList.toggle("nav-open"); });
    if (overlay) overlay.addEventListener("click", close);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
  }

  /* ---------------- Sidebar nav ---------------- */
  function buildSidebar() {
    var el = document.getElementById("sidebar-nav");
    if (!el || !NAV.length) return;

    var frag = document.createDocumentFragment();
    NAV.forEach(function (group) {
      var g = document.createElement("div");
      g.className = "nav-group";
      var title = document.createElement("div");
      title.className = "nav-group-title";
      title.textContent = group.group;
      g.appendChild(title);

      group.items.forEach(function (item) {
        var a = document.createElement("a");
        a.href = item.href;
        a.className = "nav-link" + (item.id === currentPage ? " active" : "");
        a.textContent = item.title;
        a.setAttribute("data-search", item.title.toLowerCase());
        g.appendChild(a);
      });
      frag.appendChild(g);
    });
    el.innerHTML = "";
    el.appendChild(frag);

    // active link into view
    var active = el.querySelector(".nav-link.active");
    if (active) {
      window.requestAnimationFrame(function () {
        active.scrollIntoView({ block: "center" });
      });
    }
  }

  function initSidebarSearch() {
    var input = document.getElementById("sidebar-search-input");
    if (!input) return;
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      var groups = document.querySelectorAll("#sidebar-nav .nav-group");
      groups.forEach(function (group) {
        var links = group.querySelectorAll(".nav-link");
        var visibleCount = 0;
        links.forEach(function (link) {
          var match = !q || (link.getAttribute("data-search") || "").indexOf(q) !== -1;
          link.style.display = match ? "" : "none";
          if (match) visibleCount++;
        });
        group.style.display = visibleCount ? "" : "none";
      });
    });
  }

  /* ---------------- Prev / next ---------------- */
  function flattenNav() {
    var flat = [];
    NAV.forEach(function (group) {
      group.items.forEach(function (item) { flat.push(item); });
    });
    return flat;
  }

  function buildPageNav() {
    var el = document.getElementById("page-nav");
    if (!el) return;
    var flat = flattenNav();
    var idx = -1;
    for (var i = 0; i < flat.length; i++) { if (flat[i].id === currentPage) { idx = i; break; } }
    if (idx === -1) return;
    var prev = flat[idx - 1];
    var next = flat[idx + 1];
    var html = "";
    if (prev) {
      html += '<a class="page-nav-link prev" href="' + prev.href + '">' +
        '<div class="page-nav-dir">← Previous</div>' +
        '<div class="page-nav-title">' + escapeHtml(prev.title) + "</div></a>";
    } else {
      html += "<div></div>";
    }
    if (next) {
      html += '<a class="page-nav-link next" href="' + next.href + '">' +
        '<div class="page-nav-dir">Next →</div>' +
        '<div class="page-nav-title">' + escapeHtml(next.title) + "</div></a>";
    } else {
      html += "<div></div>";
    }
    el.innerHTML = html;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---------------- Table of contents ---------------- */
  function slugify(text) {
    return text.toLowerCase().trim()
      .replace(/[`'".,()]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  function buildToc() {
    var article = document.querySelector(".prose");
    var toc = document.getElementById("toc");
    if (!article || !toc) return;

    var headings = article.querySelectorAll("h2, h3");
    if (!headings.length) { toc.style.display = "none"; return; }

    var usedIds = {};
    var frag = document.createDocumentFragment();
    var title = document.createElement("div");
    title.className = "toc-title";
    title.textContent = "On this page";
    frag.appendChild(title);

    headings.forEach(function (h) {
      var text = h.textContent.replace("#", "").trim();
      var id = h.id;
      if (!id) {
        var base = slugify(text) || "section";
        var candidate = base, n = 1;
        while (usedIds[candidate]) { candidate = base + "-" + (++n); }
        usedIds[candidate] = true;
        id = candidate;
        h.id = id;
      } else {
        usedIds[id] = true;
      }

      var anchor = document.createElement("a");
      anchor.href = "#" + id;
      anchor.className = "anchor";
      anchor.setAttribute("aria-label", "Link to this section");
      anchor.textContent = "#";
      h.appendChild(anchor);

      var link = document.createElement("a");
      link.href = "#" + id;
      link.textContent = text;
      link.className = h.tagName === "H3" ? "level-3" : "level-2";
      link.setAttribute("data-target", id);
      frag.appendChild(link);
    });

    toc.innerHTML = "";
    toc.appendChild(frag);

    // scrollspy
    var tocLinks = toc.querySelectorAll("a[data-target]");
    if ("IntersectionObserver" in window && tocLinks.length) {
      var map = {};
      tocLinks.forEach(function (l) { map[l.getAttribute("data-target")] = l; });
      var observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          var link = map[entry.target.id];
          if (!link) return;
          if (entry.isIntersecting) {
            tocLinks.forEach(function (l) { l.classList.remove("active"); });
            link.classList.add("active");
          }
        });
      }, { rootMargin: "-80px 0px -70% 0px", threshold: 0 });
      headings.forEach(function (h) { observer.observe(h); });
    }
  }

  /* ---------------- Code blocks: wrap, label, copy, highlight ---------------- */
  var KEYWORDS = ("False None True and as assert async await break class continue def del elif else " +
    "except finally for from global if import in is lambda nonlocal not or pass raise return try " +
    "while with yield self").split(" ");
  var BUILTINS = ("print len range dict list set tuple str int float bool object type isinstance " +
    "super property staticmethod classmethod Exception ValueError TypeError KeyError RuntimeError " +
    "ConnectionError TimeoutError IOError AssertionError FileNotFoundError").split(" ");

  function highlightPython(code) {
    var lines = code.split("\n").map(function (line) { return highlightPyLine(line); });
    return lines.join("\n");
  }

  function highlightPyLine(line) {
    var out = "";
    var i = 0;
    var n = line.length;
    while (i < n) {
      var ch = line[i];

      if (ch === "#") {
        out += '<span class="tok-com">' + escapeHtml(line.slice(i)) + "</span>";
        break;
      }
      if (ch === '"' || ch === "'") {
        var quote = ch, j = i + 1, triple = false;
        if (line.slice(i, i + 3) === quote + quote + quote) { triple = true; j = i + 3; }
        var end = -1;
        var search = triple ? quote + quote + quote : quote;
        var idx = line.indexOf(search, j);
        end = idx === -1 ? n : idx + search.length;
        out += '<span class="tok-str">' + escapeHtml(line.slice(i, end)) + "</span>";
        i = end;
        continue;
      }
      if (ch === "@" && /[A-Za-z_]/.test(line[i + 1] || "")) {
        var m = /^@[A-Za-z_][A-Za-z0-9_.]*/.exec(line.slice(i));
        if (m) { out += '<span class="tok-deco">' + escapeHtml(m[0]) + "</span>"; i += m[0].length; continue; }
      }
      if (/[A-Za-z_]/.test(ch)) {
        var m2 = /^[A-Za-z_][A-Za-z0-9_]*/.exec(line.slice(i));
        var word = m2[0];
        if (KEYWORDS.indexOf(word) !== -1) {
          out += '<span class="tok-kw">' + word + "</span>";
        } else if (BUILTINS.indexOf(word) !== -1) {
          out += '<span class="tok-const">' + word + "</span>";
        } else if (line[i + word.length] === "(") {
          out += '<span class="tok-fn">' + word + "</span>";
        } else if (/^[A-Z]/.test(word) && word.length > 1) {
          out += '<span class="tok-cls">' + word + "</span>";
        } else {
          out += escapeHtml(word);
        }
        i += word.length;
        continue;
      }
      if (/[0-9]/.test(ch)) {
        var m3 = /^[0-9][0-9_.]*/.exec(line.slice(i));
        out += '<span class="tok-num">' + m3[0] + "</span>";
        i += m3[0].length;
        continue;
      }
      out += escapeHtml(ch);
      i++;
    }
    return out;
  }

  function highlightBash(code) {
    return code.split("\n").map(function (line) {
      if (/^\s*#/.test(line)) return '<span class="tok-com">' + escapeHtml(line) + "</span>";
      var m = /^(\s*)(\$\s*)?([A-Za-z0-9_.\/\-]+)?/.exec(line);
      var rest = escapeHtml(line);
      // highlight simple env assignment / leading command word
      rest = rest.replace(/^([A-Za-z_][A-Za-z0-9_]*=)/, '<span class="tok-const">$1</span>');
      rest = rest.replace(/(--[a-zA-Z-]+)/g, '<span class="tok-fn">$1</span>');
      rest = rest.replace(/(&quot;[^&]*?&quot;)/g, '<span class="tok-str">$1</span>');
      return rest;
    }).join("\n");
  }

  function enhanceCodeBlocks() {
    var blocks = document.querySelectorAll(".prose pre > code, pre.raw > code");
    blocks.forEach(function (codeEl) {
      var pre = codeEl.parentElement;
      if (pre.dataset.enhanced) return;
      pre.dataset.enhanced = "1";

      var raw = codeEl.textContent.replace(/\n$/, "");
      var cls = codeEl.className || "";
      var langMatch = /language-([a-z0-9]+)/i.exec(cls);
      var lang = langMatch ? langMatch[1].toLowerCase() : "";

      var highlighted;
      if (lang === "python" || lang === "py") {
        highlighted = highlightPython(raw);
      } else if (lang === "bash" || lang === "sh" || lang === "shell") {
        highlighted = highlightBash(raw);
      } else {
        highlighted = escapeHtml(raw);
      }
      codeEl.innerHTML = highlighted;

      var wrapper = document.createElement("div");
      wrapper.className = "code-block" + (lang ? " has-head" : "");

      if (lang) {
        var head = document.createElement("div");
        head.className = "code-block-head";
        var label = document.createElement("span");
        label.textContent = lang === "py" ? "python" : lang;
        head.appendChild(label);
        head.appendChild(makeCopyButton(raw));
        wrapper.appendChild(head);
      }

      pre.parentNode.insertBefore(wrapper, pre);
      wrapper.appendChild(pre);

      if (!lang) {
        var floatBtn = makeCopyButton(raw);
        floatBtn.style.position = "absolute";
        floatBtn.style.top = "10px";
        floatBtn.style.right = "10px";
        wrapper.appendChild(floatBtn);
      }
    });
  }

  function makeCopyButton(text) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "copy-btn";
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg><span>Copy</span>';
    btn.addEventListener("click", function () {
      navigator.clipboard.writeText(text).then(function () {
        btn.classList.add("copied");
        btn.querySelector("span").textContent = "Copied";
        setTimeout(function () {
          btn.classList.remove("copied");
          btn.querySelector("span").textContent = "Copy";
        }, 1600);
      });
    });
    return btn;
  }

  /* ---------------- Wrap bare tables for horizontal scroll ---------------- */
  function wrapTables() {
    document.querySelectorAll(".prose table").forEach(function (table) {
      if (table.parentElement.classList.contains("table-wrap")) return;
      var wrap = document.createElement("div");
      wrap.className = "table-wrap";
      table.parentNode.insertBefore(wrap, table);
      wrap.appendChild(table);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initThemeToggle();
    initMobileNav();
    buildSidebar();
    initSidebarSearch();
    wrapTables();
    enhanceCodeBlocks();
    buildToc();
    buildPageNav();
  });
})();
