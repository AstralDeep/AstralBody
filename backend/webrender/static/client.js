/* Thin server-driven UI client.
 * The orchestrator renders astralprims primitives to HTML (ROTE-adapted) and
 * pushes it over the WebSocket protocol. This client inserts the
 * server-rendered `html`, merges streamed chunks (keyed by component_id when
 * bridged to a workspace identity, else stream_id), initializes
 * Plotly charts, and posts user actions back as {type:"ui_event", action, payload}.
 * No build step. */
(function () {
  "use strict";
  if (window.self !== window.top) return; // don't connect inside auth-renew iframes

  var WS_URL = (location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host + "/ws";
  var API_URL = location.origin;
  var TOKEN_KEY = "astraldeep.token";
  // The shell-injected token bootstraps the first connect; every reconnect
  // re-fetches /auth/session (which silently refreshes server-side) instead of
  // reusing a stale token. Mock-auth dev works because /auth/session answers
  // for it.
  var token = sessionStorage.getItem(TOKEN_KEY) || window.__ASTRAL_TOKEN__ || "";

  var ws = null, attempts = 0, activeChatId = null, streamSeq = {}, firstConnect = true;
  var timelineMode = false; // read-only workspace history view
  var authRetried = false;  // one silent auth_required recovery per connection
  // The server says whether this page load resumes an existing session (false
  // only right after interactive sign-in). Echoed into the first register_ui;
  // reconnects within a page are always resumes.
  var serverResumed = (window.__ASTRAL_RESUMED__ !== false);

  /** Redirect to the server-side Keycloak login, preserving the destination. */
  function gotoLogin() {
    var next = encodeURIComponent(location.pathname + location.search);
    location.href = "/auth/login?next=" + next;
  }

  /** Refresh the session token via /auth/session (server refreshes silently).
   * Calls cb(true) when authenticated; redirects to login when the session
   * is truly gone and `redirect` is set. */
  function refreshToken(redirect, cb) {
    fetch(API_URL + "/auth/session", { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j && j.authenticated && j.access_token) {
          token = j.access_token;
          try { sessionStorage.setItem(TOKEN_KEY, token); } catch (e) {}
          if (cb) cb(true);
        } else if (redirect) { gotoLogin(); }
        else if (cb) cb(false);
      })
      .catch(function () { if (cb) cb(false); });
  }

  var canvas = document.getElementById("astral-canvas");
  var chat = document.getElementById("astral-chat");
  // Shared cross-client canvas empty state: the node ships in shell.html; it is
  // detached on the first render with content and re-attached on canvas clears.
  var canvasEmpty = document.getElementById("astral-canvas-empty");
  function hideCanvasEmpty() {
    if (canvasEmpty && canvasEmpty.parentNode) canvasEmpty.parentNode.removeChild(canvasEmpty);
  }
  function showCanvasEmpty() {
    if (canvasEmpty && !canvasEmpty.parentNode) canvas.insertBefore(canvasEmpty, canvas.firstChild);
  }
  var statusEl = document.getElementById("astral-status");
  var input = document.getElementById("astral-input");
  var form = document.getElementById("astral-form");

  // ---- device detection (verbatim from useWebSocket.ts) ----
  function detectDeviceType() {
    var ua = navigator.userAgent.toLowerCase(), vw = window.innerWidth;
    if (/watch|watchos/.test(ua)) return "watch";
    if (/smart-?tv|hbbtv|netcast|viera|nettv|roku|web0s/.test(ua)) return "tv";
    if (vw <= 200) return "watch";
    if (/ipad|tablet|playbook|silk/.test(ua) || (vw > 480 && vw <= 1024 && /android/.test(ua))) return "tablet";
    if (/android|iphone|ipod|blackberry|iemobile|opera mini/.test(ua) || vw <= 480) return "mobile";
    if (vw <= 1024) return "tablet";
    return "browser";
  }
  function detectDeviceCapabilities() {
    var nav = navigator;
    return {
      device_type: detectDeviceType(),
      screen_width: window.screen.width, screen_height: window.screen.height,
      viewport_width: window.innerWidth, viewport_height: window.innerHeight,
      pixel_ratio: window.devicePixelRatio || 1,
      has_touch: (nav.maxTouchPoints || 0) > 0,
      has_geolocation: "geolocation" in navigator,
      has_microphone: !!navigator.mediaDevices, has_camera: !!navigator.mediaDevices,
      has_file_system: true,
      connection_type: (nav.connection && nav.connection.effectiveType) || "unknown",
      user_agent: navigator.userAgent,
    };
  }

  // ROTE ↔ shell cooperation, split exactly like the Android client:
  // ROTE owns per-device COMPONENT adaptation — its authoritative
  // DeviceProfile (rote_config, after register_ui) is stamped on
  // body[data-rote-device], provisionally seeded from local detection so
  // phones never flash the desktop arrangement. The SHELL owns the
  // ARRANGEMENT via body[data-astral-layout]: "stacked" below 600 CSS px
  // (Android's COMPACT window-width class → StackedShell), "split"
  // otherwise — recomputed live on resize, like Compose recomputes its
  // windowSizeClass on every configuration change.
  function applyDeviceProfile(dt) {
    if (dt) document.body.setAttribute("data-rote-device", String(dt));
  }
  function applyLayoutClass() {
    var mode = window.innerWidth < 600 ? "stacked" : "split";
    if (document.body.getAttribute("data-astral-layout") !== mode) {
      document.body.setAttribute("data-astral-layout", mode);
      if (mode === "split") { // stacked-only chrome state must not linger
        document.body.classList.remove("astral-history-open", "astral-msgs-open");
      }
    }
  }
  applyDeviceProfile(detectDeviceType());
  applyLayoutClass();
  var layoutResizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(layoutResizeTimer);
    layoutResizeTimer = setTimeout(applyLayoutClass, 120);
  });

  function setStatus(s) { if (statusEl) statusEl.textContent = s || ""; }

  function send(obj) { try { ws.send(JSON.stringify(obj)); } catch (e) {} }
  function action(name, payload) {
    send({ type: "ui_event", action: name, payload: payload || {}, session_id: activeChatId || undefined });
  }

  // ---- Plotly lazy loader: the library left the shell <head> (feature 052);
  // it is injected once on first chart need and idle-prefetched after boot ----
  var plotlyLoading = false;
  var plotlyCallbacks = [];
  function ensurePlotly(cb) {
    if (typeof Plotly !== "undefined") { if (cb) { try { cb(); } catch (e) {} } return; }
    if (cb) plotlyCallbacks.push(cb);
    if (plotlyLoading) return;
    plotlyLoading = true;
    var s = document.createElement("script");
    s.src = window.__ASTRAL_PLOTLY_URL__ || "/static/vendor/plotly.min.js";
    s.onload = function () {
      var cbs = plotlyCallbacks;
      plotlyCallbacks = [];
      for (var i = 0; i < cbs.length; i++) { try { cbs[i](); } catch (e) {} }
    };
    // allow a later chart render to retry the injection after a load failure
    s.onerror = function () { plotlyLoading = false; };
    document.head.appendChild(s);
  }
  var pendingChartRoots = [];
  function flushPendingCharts() {
    var roots = pendingChartRoots;
    pendingChartRoots = [];
    for (var i = 0; i < roots.length; i++) initCharts(roots[i]);
  }

  // ---- Plotly chart init from server-rendered data-chart placeholders ----
  function initCharts(root) {
    if (typeof Plotly === "undefined") {
      if (root.querySelectorAll(".astral-chart").length) {
        pendingChartRoots.push(root);
        ensurePlotly(flushPendingCharts);
      }
      return;
    }
    var els = root.querySelectorAll(".astral-chart");
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (el.dataset.rendered) continue;
      var kind = el.dataset.chartType, spec;
      try { spec = JSON.parse(el.dataset.chart || "{}"); } catch (e) { continue; }
      var layout = {
        autosize: true, height: window.innerWidth < 640 ? 240 : 320,
        margin: { l: 40, r: 20, t: 20, b: 40 },
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#9CA3AF" },
        xaxis: { gridcolor: "rgba(255,255,255,0.1)", tickfont: { size: 10 } },
        yaxis: { gridcolor: "rgba(255,255,255,0.1)", tickfont: { size: 10 } },
      };
      var traces, cfg = { displayModeBar: false, responsive: true };
      if (kind === "bar") traces = [{ x: spec.labels, y: spec.data, type: "bar", marker: { color: "#6366F1" } }];
      else if (kind === "line") traces = [{ x: spec.labels, y: spec.data, type: "scatter", mode: "lines+markers", marker: { color: "#6366F1" }, line: { color: "#6366F1", width: 2 } }];
      else if (kind === "pie") {
        var palette = (spec.colors && spec.colors.length) ? spec.colors : ["#6366F1", "#8B5CF6", "#06B6D4", "#10B981", "#F59E0B", "#EF4444", "#EC4899", "#3B82F6"];
        traces = [{ values: spec.data, labels: spec.labels, type: "pie", marker: { colors: palette }, textinfo: "label+percent", hole: 0.4 }];
        layout.margin = { l: 20, r: 20, t: 20, b: 20 }; layout.showlegend = true; layout.legend = { orientation: "h", y: -0.1 };
      } else if (kind === "plotly") {
        traces = spec.data || [];
        layout = Object.assign(layout, spec.layout || {});
        cfg = Object.assign(cfg, spec.config || {});
      } else continue;
      try { Plotly.newPlot(el, traces, layout, cfg); el.dataset.rendered = "1"; } catch (e) {}
    }
  }

  // ---- theme_apply: set --astral-* CSS vars from emitted banners ----
  function hexToChannels(hex) {
    var m = /^#?([0-9a-f]{6})$/i.exec((hex || "").trim());
    if (!m) return null;
    var n = parseInt(m[1], 16);
    return (n >> 16 & 255) + " " + (n >> 8 & 255) + " " + (n & 255);
  }
  var PRESETS = {
    midnight: { bg: "#0F1221", surface: "#1A1E2E", primary: "#6366F1", secondary: "#8B5CF6", text: "#F3F4F6", muted: "#9CA3AF", accent: "#06B6D4" },
    daylight: { bg: "#F8FAFC", surface: "#FFFFFF", primary: "#4F46E5", secondary: "#7C3AED", text: "#1E293B", muted: "#64748B", accent: "#0891B2" },
    ocean: { bg: "#0C1222", surface: "#132038", primary: "#0EA5E9", secondary: "#06B6D4", text: "#E2E8F0", muted: "#94A3B8", accent: "#2DD4BF" },
    sunset: { bg: "#1C1017", surface: "#2D1B24", primary: "#F97316", secondary: "#EF4444", text: "#FEF2F2", muted: "#A8A29E", accent: "#FBBF24" },
    forest: { bg: "#0F1A14", surface: "#1A2E22", primary: "#22C55E", secondary: "#10B981", text: "#ECFDF5", muted: "#86EFAC", accent: "#A3E635" },
  };
  function setColor(key, hex) { var ch = hexToChannels(hex); if (ch) document.documentElement.style.setProperty("--astral-" + key, ch); }
  function applyTheme(spec) {
    if (spec.preset && PRESETS[spec.preset]) { var p = PRESETS[spec.preset]; for (var k in p) setColor(k, p[k]); }
    else if (spec.colors) { for (var k2 in spec.colors) setColor(k2, spec.colors[k2]); }
    else if (spec.color_key && spec.color_value) setColor(spec.color_key, spec.color_value);
  }
  function processSideEffects(root) {
    initCharts(root);
    var themes = root.querySelectorAll(".astral-theme-apply");
    for (var i = 0; i < themes.length; i++) { try { applyTheme(JSON.parse(themes[i].dataset.theme || "{}")); } catch (e) {} }
  }

  // ---- render server HTML into a region ----
  function setHTML(region, htmlStr) { region.innerHTML = htmlStr || ""; processSideEffects(region); }
  function appendHTML(region, htmlStr) {
    var d = document.createElement("div"); d.innerHTML = htmlStr || "";
    region.appendChild(d); processSideEffects(d);
    region.scrollTop = region.scrollHeight;
  }
  function appendChatBubble(role, htmlStr) {
    var wrap = document.createElement("div");
    wrap.className = role === "user" ? "flex justify-end" : "flex justify-start";
    var bubble = document.createElement("div");
    bubble.className = (role === "user"
      ? "bg-astral-primary/20 border border-astral-primary/30"
      : "bg-white/5 border border-white/5") + " rounded-lg p-3 max-w-[85%] text-sm text-astral-text";
    bubble.innerHTML = htmlStr || "";
    wrap.appendChild(bubble); chat.appendChild(wrap); processSideEffects(bubble);
    chat.scrollTop = chat.scrollHeight;
  }

  // ---- query-start loading skeleton ----
  // Client-local optimistic placeholder (the Android twin's SkeletonCanvas):
  // appended to the canvas when a chat turn is sent, removed by the FIRST
  // canvas content of the turn (render/upsert/stream) or when the turn ends
  // without any (text-only answers, errors, cancellation). Reuses the
  // .astral-skeleton-line shimmer the server-driven skeleton primitive ships.
  function showSkeleton() {
    if (timelineMode || document.getElementById("astral-canvas-skeleton")) return;
    var d = document.createElement("div");
    d.id = "astral-canvas-skeleton";
    d.className = "astral-skeleton";
    d.setAttribute("role", "status");
    d.setAttribute("aria-busy", "true");
    d.setAttribute("aria-live", "polite");
    d.innerHTML = '<span class="sr-only">Loading…</span>'
      + '<div class="astral-skeleton-line h-3 w-1/3 mb-3"></div>'
      + '<div class="astral-skeleton-line h-20 w-full mb-3"></div>'
      + '<div class="astral-skeleton-line h-20 w-full mb-3"></div>'
      + '<div class="astral-skeleton-line h-3 w-1/2 mb-2"></div>';
    canvas.appendChild(d);
    canvas.scrollTop = canvas.scrollHeight;
  }
  function hideSkeleton() {
    var d = document.getElementById("astral-canvas-skeleton");
    if (d && d.parentNode) d.parentNode.removeChild(d);
  }

  // Feature 055 (uniform rule, wire-contract §1): turn start drops the
  // ephemeral welcome components (identity prefix "wel_") from the canvas.
  // SELECTIVE removal only — mid-chat the canvas holds client-side workspace
  // nodes a blanket clear would lose. Unconditional on purpose: when the
  // server flag is off the welcome arrives id-less, nothing matches, and
  // this is a no-op.
  function purgeWelcome() {
    var nodes = canvas.querySelectorAll('[data-component-id^="wel_"]');
    for (var i = 0; i < nodes.length; i++) {
      if (nodes[i].parentNode) nodes[i].parentNode.removeChild(nodes[i]);
    }
    // Legacy safety: bare-id welcome nodes sitting directly under the canvas.
    for (var j = canvas.children.length - 1; j >= 0; j--) {
      var kid = canvas.children[j];
      if (kid.id && kid.id.indexOf("wel_") === 0) canvas.removeChild(kid);
    }
  }

  // ---- workspace upsert morph ----
  // Each op targets [data-component-id]: replace the node in place when it
  // exists (no flicker, neighbors untouched), append when new, remove on op
  // 'remove'. Side effects (Plotly/theme) re-run on inserted subtrees only.
  function componentSelector(id) {
    return '[data-component-id="' + (window.CSS && CSS.escape ? CSS.escape(id) : id) + '"]';
  }
  function ensureRenderer() {
    var renderer = canvas.querySelector(".dynamic-renderer");
    if (!renderer) {
      renderer = document.createElement("div");
      renderer.className = "dynamic-renderer space-y-3";
      canvas.innerHTML = "";
      canvas.appendChild(renderer);
    }
    return renderer;
  }
  function applyUpsert(msg) {
    if (msg.chat_id && activeChatId && msg.chat_id !== activeChatId) return;
    if (timelineMode) {
      setStatus("Live workspace updated — use “Back to live” to see it.");
      return;
    }
    hideSkeleton(); // first canvas content of the turn
    var ops = msg.ops || [];
    if (ops.length) hideCanvasEmpty(); // content is arriving on the canvas
    var renderer = ensureRenderer();
    for (var i = 0; i < ops.length; i++) {
      var op = ops[i];
      if (!op || !op.component_id) continue;
      var node = canvas.querySelector(componentSelector(op.component_id));
      if (op.op === "remove") {
        if (node) node.parentNode.removeChild(node);
        continue;
      }
      if (!op.html) continue;
      var holder = document.createElement("div");
      holder.innerHTML = op.html;
      var fresh = holder.firstElementChild;
      if (!fresh) continue;
      if (node) node.replaceWith(fresh);
      else renderer.appendChild(fresh);
      processSideEffects(fresh);
    }
    syncCanvasToolbar(); // last-known flags (full renders refresh them)
  }

  // Plotly keeps per-node state and handlers; purge a node's charts before it
  // is replaced. The bundle is lazy-loaded (052) — nothing to purge before it
  // exists.
  function purgeCharts(node) {
    if (!node || typeof Plotly === "undefined") return;
    var els = node.querySelectorAll(".astral-chart");
    for (var i = 0; i < els.length; i++) {
      if (els[i].dataset.rendered) { try { Plotly.purge(els[i]); } catch (e) {} }
    }
  }

  // ---- streaming merge: replace-or-append a per-stream node keyed by stream_id ----
  // Frames carrying component_id (055 stream→artifact bridge, wire-contract
  // §2) are keyed by [data-component-id] from the FIRST frame instead — no
  // stream-<id> node ever exists for them — so the terminal persist ui_upsert
  // replaces the same node in place rather than double-rendering.
  var streamChartPlot = {}; // stream_id → last chart re-plot ms (interim ≤1/s)
  function mergeStream(msg) {
    var htmlStr = msg.html || "";
    if (msg.error) {
      htmlStr = '<div class="text-xs text-red-400 border border-red-500/20 rounded p-2">' +
        escapeText(msg.error.message || "stream error") + "</div>";
    }
    if (msg.component_id) { mergeKeyedStream(msg, htmlStr); return; }
    var id = "stream-" + msg.stream_id;
    var node = document.getElementById(id);
    if (!htmlStr && !msg.terminal) return;
    hideSkeleton(); // streamed canvas content counts as the first component
    if (node) { node.innerHTML = htmlStr; processSideEffects(node); }
    else if (htmlStr) {
      hideCanvasEmpty();
      node = document.createElement("div"); node.id = id; node.innerHTML = htmlStr;
      canvas.appendChild(node); processSideEffects(node);
    }
  }
  function mergeKeyedStream(msg, htmlStr) {
    if (msg.terminal) delete streamChartPlot[msg.stream_id];
    else if (htmlStr.indexOf("astral-chart") !== -1) {
      // Chart-bearing interim frames re-plot at most once per second per
      // stream (leak/flicker guard); the terminal frame always renders.
      var now = Date.now();
      if (now - (streamChartPlot[msg.stream_id] || 0) < 1000) return;
      streamChartPlot[msg.stream_id] = now;
    }
    if (!htmlStr) return; // empty terminal: keep the last content for the persist upsert
    hideSkeleton(); // streamed canvas content counts as the first component
    var node = canvas.querySelector(componentSelector(msg.component_id));
    var holder = document.createElement("div");
    holder.innerHTML = htmlStr;
    var fresh = holder.firstElementChild;
    if (!fresh) return;
    if (holder.children.length > 1 ||
        fresh.getAttribute("data-component-id") !== msg.component_id) {
      // Client-built error html (and any fragment the server did not wrap)
      // still needs the identity anchor or later frames would append copies.
      fresh = document.createElement("div");
      fresh.setAttribute("data-component-id", msg.component_id);
      while (holder.firstChild) fresh.appendChild(holder.firstChild);
    }
    purgeCharts(node);
    if (node) node.replaceWith(fresh);
    else { hideCanvasEmpty(); ensureRenderer().appendChild(fresh); }
    processSideEffects(fresh);
  }

  // ---- incoming messages ----
  function onMessage(ev) {
    var data; try { data = JSON.parse(ev.data); } catch (e) { return; }
    switch (data.type) {
      case "ui_render":
        if (data.target === "chat") appendChatBubble("assistant", data.html);
        else if (data.target === "history") { var hr = document.getElementById("astral-history"); if (hr) setHTML(hr, data.html); }
        else {
          hideSkeleton(); setHTML(canvas, data.html);
          // Emptiness comes from the STRUCTURED payload: render_workspace
          // emits a truthy wrapper div even for zero components (055), so
          // html truthiness only decides frames without a components array.
          if (Array.isArray(data.components) ? !data.components.length : !data.html) showCanvasEmpty();
          readCanvasFlags(); syncCanvasToolbar();
        }
        break;
      case "ui_upsert": applyUpsert(data); break; // in-place workspace updates
      case "ui_update":
        hideSkeleton(); setHTML(canvas, data.html); if (!data.html) showCanvasEmpty();
        readCanvasFlags(); syncCanvasToolbar();
        break;
      case "ui_append": hideSkeleton(); hideCanvasEmpty(); appendHTML(canvas, data.html); break;
      case "workspace_timeline_mode": // read-only history view
        timelineMode = !!data.active;
        if (timelineMode) hideSkeleton();
        setStatus(timelineMode ? "Viewing workspace history (read-only)" : "");
        syncCanvasToolbar(); // export/share chrome hides in the read-only view
        break;
      case "chat_deleted": // chat removed (possibly from another tab)
        if (data.chat_id && data.chat_id === activeChatId) {
          activeChatId = null; timelineMode = false;
          setHTML(canvas, "");
          showCanvasEmpty();
          setStatus("This chat was deleted.");
        }
        break;
      case "auth_required": // recoverable WS auth failure
        if (!authRetried) {
          authRetried = true;
          refreshToken(true, function (ok) {
            if (ok && ws && ws.readyState === 1) {
              send({ type: "register_ui", token: token, capabilities: ["render", "stream"],
                     session_id: "ui-" + Date.now(), device: detectDeviceCapabilities(), resumed: true });
            } else if (ok) { try { ws.close(); } catch (e) {} }
          });
        } else { gotoLogin(); }
        break;
      case "ui_stream_data": {
        if (data.session_id && activeChatId && data.session_id !== activeChatId) return;
        var last = streamSeq[data.stream_id]; if (last == null) last = -1;
        if (data.seq <= last) return; streamSeq[data.stream_id] = data.seq;
        mergeStream(data);
        if (data.terminal) delete streamSeq[data.stream_id];
        break;
      }
      case "stream_subscribed": {
        // component_id-bridged streams get a keyed placeholder (wire-contract
        // §2) so the first frame and the terminal persist upsert replace it
        // in place; legacy subscriptions need no node until data arrives.
        if (!data.component_id) break;
        if (data.session_id && activeChatId && data.session_id !== activeChatId) break;
        if (canvas.querySelector(componentSelector(data.component_id))) break;
        hideSkeleton(); hideCanvasEmpty();
        var ph = document.createElement("div");
        ph.setAttribute("data-component-id", data.component_id);
        ph.innerHTML = '<div class="astral-skeleton" role="status" aria-busy="true">'
          + '<span class="sr-only">Loading…</span>'
          + '<div class="astral-skeleton-line h-20 w-full"></div></div>';
        ensureRenderer().appendChild(ph);
        break;
      }
      case "chrome_render": // server-rendered chrome regions
        if (data.region === "modal") setModal(data.html || "");
        else if (data.region === "topbar") {
          var tb = document.getElementById("astral-topbar");
          if (tb) { tb.innerHTML = data.html || ""; }
        }
        break;
      case "chat_status":
        // A turn that ends with no canvas output (text-only answer, error,
        // cancellation) must still clear the query-start skeleton.
        if (data.status === "done" || data.status === "idle") hideSkeleton();
        if (data.status === "processing_async") {
          // Background dispatch ack (055): status text only — never the turn
          // lock (no skeleton), so the user can keep chatting or switch chats.
          hideSkeleton();
          setStatus("Running in background…");
          break;
        }
        setStatus({ idle: "", thinking: "Thinking…", executing: "Working…", done: "" }[data.status] || "");
        break;
      case "chat_step": renderStep(data.step); break;
      case "chat_created": if (data.payload) { activeChatId = data.payload.chat_id; } break;
      case "chat_loaded":
        activeChatId = data.chat && data.chat.id; chat.innerHTML = ""; canvas.innerHTML = "";
        showCanvasEmpty(); // cleared canvas; the workspace ui_render (if any) replaces it
        timelineMode = false; setStatus("");
        // The chat rail is TEXT ONLY. Component messages carry a
        // server-rendered `html` form containing only their text primitives
        // (the server drops rich components); a turn whose output was purely
        // rich gets no `html` and renders no bubble here — it lives on the
        // canvas, which re-hydrates via the ui_render the server pushes right
        // after.
        if (data.chat && data.chat.messages) data.chat.messages.forEach(function (m) {
          // Re-hydrated attachment chip leads the user's message on its own
          // line (consistent with the live-send rendering above).
          var attChip = "";
          if (m.attachments && m.attachments.length) {
            attChip = attachChipHtml(m.attachments.map(function (a) { return a.filename; }).join(", "));
          }
          if (typeof m.content === "string") {
            appendChatBubble(m.role, attChip + (m.content ? "<div>" + escapeText(m.content) + "</div>" : ""));
          } else if (m.html) {
            appendChatBubble(m.role, attChip + m.html);
          } else if (attChip) {
            // Component-only message with no text — keep just the attachment chip.
            appendChatBubble(m.role, attChip);
          }
          // else: a rich-component-only turn — shown on the canvas, no chat bubble.
        });
        break;
      case "user_preferences":
        if (data.preferences && data.preferences.theme) applyTheme(data.preferences.theme);
        break;
      case "error": { // feature 044 FR-002 — server error replies are never silent
        var em = errorMessage(data);
        showToast(em, "error");
        hideSkeleton(); // the turn is over; no components are coming
        setStatus(""); // resolve any stuck "Thinking…" state (SC-006)
        break;
      }
      case "notification": // scheduler push (feature 044 parity matrix)
        showToast((data.title ? data.title + ": " : "") + (data.body || ""), data.level === "error" ? "error" : "info");
        break;
      case "task_started": { // 055: background dispatch accepted (any device)
        var tsp = data.payload || {};
        addTaskChip(tsp.task_id, tsp.chat_id, tsp.title);
        showToast("Running in background — you will be notified when it finishes.", "info");
        break;
      }
      case "task_completed": { // 055: background task finished (any device)
        var tcp = data.payload || {};
        if (tcp.task_id) {
          if (bgTaskDone[tcp.task_id]) break; // watcher + fan-out duplicate
          bgTaskDone[tcp.task_id] = true;
          removeTaskChip(tcp.task_id);
        }
        var tcFail = tcp.status === "failed";
        var tcMsg = tcp.summary || ("Background task " + (tcp.status || "completed"));
        if (tcp.chat_id && tcp.chat_id === activeChatId) {
          showToast(tcMsg, tcFail ? "error" : "info");
          // Pull the narrative/canvas the task persisted while detached.
          action("load_chat", { chat_id: tcp.chat_id });
        } else if (tcp.chat_id) {
          showToast(tcMsg + " — tap to open", tcFail ? "error" : "info", function () {
            action("load_chat", { chat_id: tcp.chat_id }); // recents-click path
            closeHistoryOverlay();
          });
        } else {
          showToast(tcMsg, tcFail ? "error" : "info");
        }
        break;
      }
      case "tool_progress": { // long-running job update (fan-out is chat-scoped)
        var tpChat = data.session_id || data.chat_id;
        if (tpChat && activeChatId && tpChat !== activeChatId) break;
        if (data.terminal) { setStatus(""); break; } // outcome lands as a persisted upsert
        var tpText = data.message || ((data.tool_name || "job") + " running…");
        if (typeof data.percentage === "number") tpText += " (" + Math.round(data.percentage) + "%)";
        setStatus(tpText);
        break;
      }
      case "rote_config": // ROTE's device verdict drives the shell layout
        applyDeviceProfile(data.device_profile && data.device_profile.device_type);
        break;
      case "system_config": case "agent_list": case "agent_registered":
      case "history_list": case "heartbeat": case "llm_config_ack": case "saved_components_list":
        break; // not needed for the core flow
      default: break;
    }
  }

  // Normalize the three historical error-frame shapes (see
  // backend/shared/ui_protocol.json): {code,message} | {payload:{message}} | {message}.
  function errorMessage(data) {
    var m = data.message || (data.payload && data.payload.message) || "Something went wrong.";
    return data.code && data.code !== "internal" ? m + " (" + data.code + ")" : m;
  }

  var toastHost = null;
  /** onTap (optional) makes the toast a tap-to-open affordance (055
   *  background completions); tappable toasts linger longer. */
  function showToast(message, kind, onTap) {
    if (!message) return;
    if (!toastHost) {
      toastHost = document.createElement("div");
      toastHost.id = "astral-toasts";
      toastHost.setAttribute("role", "status");
      toastHost.style.cssText = "position:fixed;bottom:16px;right:16px;z-index:9999;display:flex;flex-direction:column;gap:8px;max-width:360px;";
      document.body.appendChild(toastHost);
    }
    var t = document.createElement("div");
    t.className = "astral-toast astral-toast-" + (kind || "info");
    t.style.cssText = "padding:10px 14px;border-radius:8px;font-size:13px;color:#fff;box-shadow:0 4px 14px rgba(0,0,0,.4);"
      + (kind === "error" ? "background:#7f1d1d;border:1px solid #b91c1c;" : "background:#1e293b;border:1px solid #334155;");
    t.textContent = message;
    if (onTap) {
      t.style.cursor = "pointer";
      t.setAttribute("role", "button");
      t.tabIndex = 0;
      var fire = function () { if (t.parentNode) t.parentNode.removeChild(t); onTap(); };
      t.addEventListener("click", fire);
      t.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fire(); }
      });
    }
    toastHost.appendChild(t);
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, onTap ? 12000 : 6000);
  }

  function escapeText(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : String(s); return d.innerHTML; }

  // Render attachment(s) as a pill on its own line above the request text (a
  // plain "📎 name" prefix collapses onto the query line because chat bubbles
  // don't preserve newlines).
  function attachChipHtml(names) {
    return "<div class=\"mb-1\"><span class=\"inline-flex items-center gap-1 rounded "
      + "bg-white/10 border border-white/10 px-2 py-0.5 text-xs\">📎 "
      + escapeText(names) + "</span></div>";
  }

  var stepEls = {};
  function renderStep(step) {
    if (!step) return;
    var el = stepEls[step.id];
    if (!el) {
      el = document.createElement("div");
      el.className = "text-xs text-astral-muted/70 px-2 py-1";
      chat.appendChild(el); stepEls[step.id] = el;
    }
    var icon = step.status === "completed" ? "✓" : step.status === "errored" ? "✗" : "•";
    // Chat shows only the tool/step name; result summaries stay in the
    // persisted step record (chat-steps API / audit), not the transcript.
    el.textContent = icon + " " + (step.name || step.kind || "step");
    chat.scrollTop = chat.scrollHeight;
  }

  // ---- outgoing: chat + delegated component actions ----
  // A message may carry staged attachments (see the attachment block lower
  // down). readyAttachments()/clearStagedAttachments() are declared there;
  // function/var hoisting makes them available here at call time.
  function sendChat(message) {
    var ready = (typeof readyAttachments === "function") ? readyAttachments() : [];
    if (!message && !ready.length) return;
    var html = "";
    if (ready.length) {
      var names = ready.map(function (a) { return a.filename; }).join(", ");
      html += attachChipHtml(names);  // pill on its own line above the request
    }
    if (message) html += "<div>" + escapeText(message) + "</div>";
    appendChatBubble("user", html);
    var payload = { message: message || "", chat_id: activeChatId };
    if (ready.length) {
      payload.attachments = ready.map(function (a) {
        return { attachment_id: a.attachment_id, filename: a.filename, category: a.category };
      });
    }
    if (bgArmed) payload.async_mode = true; // one-shot background-run arming (055)
    send({ type: "ui_event", action: "chat_message", session_id: activeChatId || undefined, payload: payload });
    purgeWelcome(); // 055 uniform rule: welcome never survives the first send
    // Async turns never lock the composer: no skeleton — the processing_async
    // ack drives the status line instead.
    if (bgArmed) setBgArmed(false);
    else showSkeleton(); // optimistic loading state until the first canvas content
    if (typeof clearStagedAttachments === "function") clearStagedAttachments();
  }

  if (form) form.addEventListener("submit", function (e) {
    e.preventDefault();
    var v = input.value.trim();
    var hasReady = (typeof readyAttachments === "function") && readyAttachments().length;
    if (!v && !hasReady) return;
    input.value = "";
    sendChat(v);
  });

  // ---- new chat (topbar button) — the web twin of the native clients' ＋ New:
  // clear the local conversation state, then ask the server for a fresh chat
  // (it replies chat_created, which sets activeChatId).
  var newChatBtn = document.getElementById("astral-newchat-btn");
  if (newChatBtn) newChatBtn.addEventListener("click", function () {
    activeChatId = null;
    timelineMode = false;
    streamSeq = {};
    streamChartPlot = {};
    stepEls = {};
    hideSkeleton();
    chat.innerHTML = "";
    canvas.innerHTML = "";
    setStatus("");
    action("new_chat", {});
    closeHistoryOverlay();
    if (input) { try { input.focus(); } catch (e) {} }
  });

  // ---- stacked-shell chrome: the web twin of Android's StackedShell.
  // Recent chats live behind the topbar speech-bubble button (full-screen
  // overlay of the same server-rendered #astral-history region), and the
  // transcript collapses behind a "Messages (N)" bar above the input.
  // Split layouts never see these controls — astral.css gates them on
  // body[data-astral-layout="stacked"].
  function closeHistoryOverlay() {
    document.body.classList.remove("astral-history-open");
    if (chatsBtn) chatsBtn.setAttribute("aria-expanded", "false");
  }
  var chatsBtn = document.getElementById("astral-chats-btn");
  if (chatsBtn) chatsBtn.addEventListener("click", function () {
    var topbar = document.getElementById("astral-topbar");
    if (topbar) document.documentElement.style.setProperty("--astral-topbar-h", topbar.offsetHeight + "px");
    var open = document.body.classList.toggle("astral-history-open");
    chatsBtn.setAttribute("aria-expanded", open ? "true" : "false");
  });
  var msgsToggle = document.getElementById("astral-msgs-toggle");
  var msgsLabel = document.getElementById("astral-msgs-label");
  if (msgsToggle) msgsToggle.addEventListener("click", function () {
    var open = document.body.classList.toggle("astral-msgs-open");
    msgsToggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (open && chat) chat.scrollTop = chat.scrollHeight;
  });
  function syncMsgsToggle() {
    if (!msgsToggle || !chat) return;
    var n = chat.children.length;
    msgsToggle.hidden = n === 0;
    if (n === 0) document.body.classList.remove("astral-msgs-open");
    if (msgsLabel) msgsLabel.textContent = n ? "Messages (" + n + ")" : "Messages";
  }
  if (window.MutationObserver && chat) new MutationObserver(syncMsgsToggle).observe(chat, { childList: true });
  syncMsgsToggle();

  // Delegated handlers for server-rendered interactive primitives
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest(".astral-action");
    if (btn) {
      var act = btn.getAttribute("data-action"); var payload = {};
      try { payload = JSON.parse(btn.getAttribute("data-payload") || "{}"); } catch (_) {}
      // Actions emitted inside a workspace component carry its identity;
      // historical views are inert except chrome actions.
      var compHost = btn.closest && btn.closest("[data-component-id]");
      if (compHost && !payload.component_id) payload.component_id = compHost.getAttribute("data-component-id");
      if (!payload.chat_id && activeChatId) payload.chat_id = activeChatId;
      if (timelineMode && compHost && act && act.indexOf("chrome_") !== 0) {
        setStatus("Read-only history view — go back to live to interact.");
        return;
      }
      // A chat_message action (e.g. the welcome examples' buttons) is exactly
      // a typed message — present it the same way: user bubble + the standard
      // chat payload shape.
      if (act === "chat_message" && payload.message) { sendChat(payload.message); return; }
      if (act === "chrome_open") showModalSkeleton(act, payload);
      if (act) action(act, payload);
      if (act === "load_chat") closeHistoryOverlay(); // mobile: leave the full-screen list
      return;
    }
    // param_picker toggle buttons (checklist)
    var chip = e.target.closest && e.target.closest(".astral-pp-field[data-kind='checklist']");
    if (chip) { var on = chip.getAttribute("aria-pressed") === "true"; chip.setAttribute("aria-pressed", on ? "false" : "true");
      chip.classList.toggle("bg-astral-primary/30"); chip.classList.toggle("border-astral-primary"); chip.classList.toggle("text-white"); return; }
    // param_picker submit
    var sub = e.target.closest && e.target.closest(".astral-pp-submit");
    if (sub) { submitParamPicker(sub.closest(".astral-param-picker")); return; }
    // table pagination
    var pgPrev = e.target.closest && e.target.closest(".astral-page-prev");
    var pgNext = e.target.closest && e.target.closest(".astral-page-next");
    if (pgPrev || pgNext) { paginate(e.target.closest(".astral-pagination"), pgNext ? 1 : -1); return; }
  });
  document.addEventListener("change", function (e) {
    if (e.target.classList && e.target.classList.contains("astral-page-size")) {
      paginateSize(e.target.closest(".astral-pagination"), parseInt(e.target.value, 10));
    }
    if (e.target.classList && e.target.classList.contains("astral-color-picker")) {
      var key = e.target.getAttribute("data-color-key"); setColor(key, e.target.value);
      action("save_theme", { theme: { color_key: key, color_value: e.target.value } });
    }
  });

  function collectFields(form) {
    var state = {};
    form.querySelectorAll(".astral-pp-field").forEach(function (f) {
      var name = f.getAttribute("data-field"), kind = f.getAttribute("data-kind");
      if (!name) return;
      if (kind === "boolean") state[name] = f.checked;
      else if (kind === "number") state[name] = f.value === "" ? null : Number(f.value);
      else if (kind === "checklist") { state[name] = state[name] || []; if (f.getAttribute("aria-pressed") === "true") state[name].push(f.getAttribute("data-value")); }
      else state[name] = f.value;
    });
    return state;
  }
  function submitParamPicker(form) {
    if (!form) return;
    var template = form.getAttribute("data-template") || "";
    var state = collectFields(form);
    var msg = template.replace("{__values_json__}", JSON.stringify(state, null, 2));
    msg = msg.replace(/\{(\w+)\}/g, function (m, k) {
      if (!(k in state)) return m; var v = state[k];
      return typeof v === "string" ? v : JSON.stringify(v);
    });
    sendChat(msg);
  }
  // Pagination carries the table's component identity so the server updates
  // ONLY that table in place via the standardized component_action pipeline.
  function paginateComponentId(el) {
    var host = el && el.closest && el.closest("[data-component-id]");
    return host ? host.getAttribute("data-component-id") : null;
  }
  function paginate(el, dir) {
    if (!el) return; var ctx; try { ctx = JSON.parse(el.getAttribute("data-ctx") || "{}"); } catch (e) { return; }
    if (timelineMode) { setStatus("Read-only history view — go back to live to interact."); return; }
    var size = ctx.page_size, off = Math.max(0, (ctx.page_offset || 0) + dir * size);
    action("table_paginate", { tool_name: ctx.source_tool, agent_id: ctx.source_agent,
      component_id: paginateComponentId(el), chat_id: activeChatId,
      params: Object.assign({}, ctx.source_params, { limit: size, offset: off }) });
  }
  function paginateSize(el, size) {
    if (!el) return; var ctx; try { ctx = JSON.parse(el.getAttribute("data-ctx") || "{}"); } catch (e) { return; }
    if (timelineMode) { setStatus("Read-only history view — go back to live to interact."); return; }
    action("table_paginate", { tool_name: ctx.source_tool, agent_id: ctx.source_agent,
      component_id: paginateComponentId(el), chat_id: activeChatId,
      params: Object.assign({}, ctx.source_params, { limit: size, offset: 0 }) });
  }

  // ---- 055 US4/US5: component chrome (refine / history / export / share) ----
  // The server renders the affordances (flag-gated, renderer.py
  // _component_chrome); this block owns their click behavior. The instruction
  // capture is an inline popover (same idiom as the paperclip menu — the
  // codebase never uses window.prompt/alert).
  var chromePop = null;
  function closeChromePop() {
    if (chromePop && chromePop.parentNode) chromePop.parentNode.removeChild(chromePop);
    chromePop = null;
  }
  function openChromePop(anchor) {
    closeChromePop();
    var row = anchor.parentNode; // the .astral-component-chrome affordance row
    if (row && !row.style.position) row.style.position = "relative";
    chromePop = document.createElement("div");
    chromePop.className = "astral-chrome-pop";
    chromePop.style.cssText = "position:absolute;right:0;bottom:100%;margin-bottom:6px;z-index:40;"
      + "min-width:260px;max-width:340px;padding:10px;border-radius:10px;"
      + "background:rgb(var(--astral-surface,26 30 46));border:1px solid rgba(255,255,255,.12);"
      + "box-shadow:0 8px 24px rgba(0,0,0,.45);font-size:13px;";
    (row || document.body).appendChild(chromePop);
    return chromePop;
  }
  function chromePopButton(text, primary) {
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = text;
    b.style.cssText = "font-size:12px;border-radius:8px;padding:4px 10px;cursor:pointer;"
      + (primary ? "background:rgb(var(--astral-primary,99 102 241));border:0;color:#fff;"
                 : "background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);color:inherit;");
    return b;
  }
  function chromeComponentId(el) {
    var host = el.closest && el.closest("[data-component-id]");
    return host ? host.getAttribute("data-component-id") : null;
  }

  function openRefinePrompt(btn) {
    if (timelineMode) { setStatus("Read-only history view — go back to live to interact."); return; }
    var cid = chromeComponentId(btn);
    if (!cid) return;
    var pop = openChromePop(btn);
    var label = document.createElement("div");
    label.textContent = "Describe the change to this component";
    label.style.cssText = "font-size:12px;margin-bottom:6px;opacity:.8;";
    var inp = document.createElement("input");
    inp.type = "text";
    inp.placeholder = "e.g. add a totals row";
    inp.style.cssText = "width:100%;box-sizing:border-box;font-size:13px;padding:6px 8px;border-radius:8px;"
      + "background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);color:inherit;";
    var rowEl = document.createElement("div");
    rowEl.style.cssText = "display:flex;justify-content:flex-end;gap:8px;margin-top:8px;";
    var cancel = chromePopButton("Cancel", false);
    var go = chromePopButton("Refine", true);
    function submit() {
      var text = (inp.value || "").trim();
      if (!text) { inp.focus(); return; }
      action("component_refine", { component_id: cid, instruction: text, chat_id: activeChatId });
      closeChromePop();
      showToast("Refining component…", "info");
    }
    go.addEventListener("click", submit);
    cancel.addEventListener("click", closeChromePop);
    inp.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); submit(); }
      else if (e.key === "Escape") { e.stopPropagation(); closeChromePop(); }
    });
    pop.appendChild(label); pop.appendChild(inp); pop.appendChild(rowEl);
    rowEl.appendChild(cancel); rowEl.appendChild(go);
    inp.focus();
  }

  function openHistoryList(btn) {
    if (timelineMode) { setStatus("Read-only history view — go back to live to interact."); return; }
    var cid = chromeComponentId(btn);
    if (!cid) return;
    var versions = [];
    try { versions = JSON.parse(btn.getAttribute("data-versions") || "[]"); } catch (e) {}
    var pop = openChromePop(btn);
    var label = document.createElement("div");
    label.textContent = "Version history";
    label.style.cssText = "font-size:12px;margin-bottom:6px;opacity:.8;";
    pop.appendChild(label);
    if (!versions.length) {
      var none = document.createElement("div");
      none.textContent = "No earlier versions yet — refine the component to create one.";
      none.style.cssText = "font-size:12px;opacity:.6;";
      pop.appendChild(none);
      return;
    }
    versions.forEach(function (v) {
      if (!v || v.version_no == null) return;
      var b = document.createElement("button");
      b.type = "button";
      var when = String(v.created_at || "").replace("T", " ").slice(0, 16);
      b.textContent = "v" + v.version_no
        + (v.title ? " · " + v.title : "")
        + (when ? " · " + when : "");
      b.title = "Restore this version" + (v.reason ? " (archived on " + v.reason + ")" : "");
      b.style.cssText = "display:block;width:100%;text-align:left;font-size:12px;padding:6px 8px;"
        + "border-radius:8px;background:transparent;border:0;color:inherit;cursor:pointer;";
      b.addEventListener("click", function () {
        action("component_restore", { component_id: cid, version_no: v.version_no, chat_id: activeChatId });
        closeChromePop();
        showToast("Restoring version " + v.version_no + "…", "info");
      });
      pop.appendChild(b);
    });
  }

  // Exports are authenticated downloads: fetch with the bearer token, then
  // hand the blob to a temporary <a download> (a plain href can't carry auth).
  function exportDownload(path, filename, appendChat) {
    var url = path;
    if (appendChat) {
      if (!activeChatId) { showToast("Open a chat first — nothing to export yet.", "error"); return; }
      url += (url.indexOf("?") === -1 ? "?" : "&") + "chat_id=" + encodeURIComponent(activeChatId);
    }
    fetch(API_URL + url, { headers: { Authorization: "Bearer " + token }, credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok) throw new Error("Export failed (" + r.status + ")");
        return r.blob();
      })
      .then(function (blob) {
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = filename || "export";
        document.body.appendChild(a);
        a.click();
        setTimeout(function () {
          URL.revokeObjectURL(a.href);
          if (a.parentNode) a.parentNode.removeChild(a);
        }, 1000);
      })
      .catch(function (err) { showToast(String((err && err.message) || err), "error"); });
  }

  function mintShare(scope, componentId) {
    if (!activeChatId) { showToast("Open a chat first — nothing to share yet.", "error"); return; }
    var body = { chat_id: activeChatId, scope: scope };
    if (componentId) body.component_id = componentId;
    fetch(API_URL + "/api/share", {
      method: "POST",
      headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body),
    })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; });
      })
      .then(function (res) {
        if (!res.ok) {
          var msg = res.body && res.body.error === "phi_blocked"
            ? "Sharing refused: the content matched the PHI gate."
            : (res.body && (res.body.detail || res.body.error)) || ("Share failed (" + res.status + ")");
          showToast(msg, "error");
          return;
        }
        var shareUrl = res.body && res.body.share_url;
        if (!shareUrl) { showToast("Share failed: no link returned.", "error"); return; }
        var abs = shareUrl.indexOf("http") === 0 ? shareUrl : API_URL + shareUrl;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(abs).then(
            function () { showToast("Share link copied to clipboard.", "info"); },
            function () { showToast("Share link: " + abs, "info"); });
        } else { showToast("Share link: " + abs, "info"); }
      })
      .catch(function () { showToast("Couldn't create the share link.", "error"); });
  }

  // Canvas toolbar (export page / share page). The server stamps the flag
  // state as data-astral-export / data-astral-share on the .dynamic-renderer
  // root of every full canvas render (renderer.py _workspace_flag_attrs);
  // the toolbar exists only while a flagged renderer is on the canvas.
  var canvasFlags = { exp: false, share: false };
  function readCanvasFlags() {
    var r = canvas.querySelector(".dynamic-renderer");
    canvasFlags.exp = !!(r && r.getAttribute("data-astral-export"));
    canvasFlags.share = !!(r && r.getAttribute("data-astral-share"));
  }
  function syncCanvasToolbar() {
    var bar = document.getElementById("astral-canvas-toolbar");
    var want = (canvasFlags.exp || canvasFlags.share) && !timelineMode
      && !!canvas.querySelector(".dynamic-renderer");
    if (!want) {
      if (bar && bar.parentNode) bar.parentNode.removeChild(bar);
      return;
    }
    if (bar) return; // already up
    bar = document.createElement("div");
    bar.id = "astral-canvas-toolbar";
    bar.style.cssText = "position:sticky;top:0;z-index:5;display:flex;justify-content:flex-end;gap:8px;padding:2px 4px;";
    if (canvasFlags.exp) bar.appendChild(chromeToolbarButton("⬇ Export page", "astral-export-canvas", null));
    if (canvasFlags.share) bar.appendChild(chromeToolbarButton("↗ Share page", "astral-share-btn", "canvas"));
    canvas.insertBefore(bar, canvas.firstChild);
  }
  function chromeToolbarButton(text, cls, shareScope) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = cls;
    b.textContent = text;
    if (shareScope) b.setAttribute("data-share-scope", shareScope);
    b.style.cssText = "font-size:11px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);"
      + "border-radius:8px;padding:3px 10px;color:inherit;cursor:pointer;";
    return b;
  }

  document.addEventListener("click", function (e) {
    var t = e.target;
    var refine = t.closest && t.closest(".astral-refine-btn");
    if (refine) { openRefinePrompt(refine); return; }
    var hist = t.closest && t.closest(".astral-vhistory-btn");
    if (hist) { openHistoryList(hist); return; }
    var csv = t.closest && t.closest(".astral-export-csv");
    if (csv) {
      e.preventDefault();
      var cid = chromeComponentId(csv);
      exportDownload(csv.getAttribute("href"), (cid || "table") + ".csv", true);
      return;
    }
    var expCanvas = t.closest && t.closest(".astral-export-canvas");
    if (expCanvas) {
      if (!activeChatId) { showToast("Open a chat first — nothing to export yet.", "error"); return; }
      exportDownload("/api/export/canvas/" + encodeURIComponent(activeChatId) + ".html",
        "canvas-" + activeChatId + ".html", false);
      return;
    }
    var share = t.closest && t.closest(".astral-share-btn");
    if (share) {
      mintShare(share.getAttribute("data-share-scope") || "component", chromeComponentId(share));
      return;
    }
    if (chromePop && !chromePop.contains(t)) closeChromePop();
  });

  // Attachment staging: paperclip → pick → upload → chip → send as structured
  // attachments[] on the next chat_message.
  var stagedAttachments = [];   // {uid, attachment_id|null, filename, category, state, note}
  var attachSeq = 0;
  var MAX_ATTACHMENTS = 10;
  var attachEl = document.getElementById("astral-attachments");
  var attachBtn = document.getElementById("astral-attach-btn");
  var attachInput = document.getElementById("astral-attach-input");

  function readyAttachments() {
    return stagedAttachments.filter(function (a) { return a.state === "ready" && a.attachment_id; });
  }
  function clearStagedAttachments() {
    stagedAttachments = [];
    renderAttachments();
  }
  function removeStaged(uid) {
    stagedAttachments = stagedAttachments.filter(function (a) { return a.uid !== uid; });
    renderAttachments();
  }
  function renderAttachments() {
    if (!attachEl) return;
    attachEl.innerHTML = "";
    if (!stagedAttachments.length) { attachEl.classList.add("hidden"); return; }
    attachEl.classList.remove("hidden");
    stagedAttachments.forEach(function (a) {
      var chip = document.createElement("span");
      chip.className = "astral-chip is-" + a.state;
      chip.setAttribute("data-uid", String(a.uid));
      var name = document.createElement("span");
      name.className = "astral-chip-name";
      name.textContent = a.filename;
      name.title = a.note || a.filename;
      chip.appendChild(name);
      var state = document.createElement("span");
      state.className = "astral-chip-state";
      state.textContent = a.state === "uploading" ? "…" :
                          a.state === "failed" ? "failed" :
                          (a.note ? a.note : "");
      chip.appendChild(state);
      var x = document.createElement("button");
      x.type = "button";
      x.className = "astral-chip-remove";
      x.setAttribute("aria-label", "Remove " + a.filename);
      x.setAttribute("data-remove-uid", String(a.uid));
      x.textContent = "×";
      chip.appendChild(x);
      attachEl.appendChild(chip);
    });
  }

  function uploadStagedFile(file) {
    var entry = { uid: ++attachSeq, attachment_id: null, filename: file.name,
                  category: "file", state: "uploading", note: "" };
    stagedAttachments.push(entry);
    renderAttachments();
    var fd = new FormData(); fd.append("file", file);
    fetch(API_URL + "/api/upload", { method: "POST", headers: { Authorization: "Bearer " + token }, body: fd })
      .then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; });
      })
      .then(function (res) {
        if (!res.ok) {
          entry.state = "failed";
          entry.note = (res.body && (res.body.detail || res.body.message)) || ("error " + res.status);
          setStatus("Couldn't attach " + file.name + ": " + entry.note);
          renderAttachments();
          return;
        }
        var j = res.body || {};
        entry.attachment_id = j.attachment_id || null;
        entry.category = j.category || "file";
        entry.state = entry.attachment_id ? "ready" : "failed";
        // Surface the eager auto-parser status (US2) on the chip.
        var ps = j.parser_status;
        if (ps === "preparing") entry.note = "preparing reader…";
        else if (ps === "pending_admin_approval") entry.note = "reader pending admin";
        else if (ps === "unavailable") entry.note = "no reader yet";
        else entry.note = "";
        if (!entry.attachment_id) entry.note = "upload failed";
        renderAttachments();
      })
      .catch(function () {
        entry.state = "failed"; entry.note = "network error";
        setStatus("Couldn't attach " + file.name);
        renderAttachments();
      });
  }

  // Paperclip → small menu: upload a new file, or choose an existing one (US3).
  var attachMenu = null;
  function closeAttachMenu() { if (attachMenu) { attachMenu.remove(); attachMenu = null; } }
  function openAttachMenu() {
    closeAttachMenu();
    attachMenu = document.createElement("div");
    attachMenu.className = "astral-attach-menu";
    [["Upload a file", function () { attachInput.click(); }],
     ["Choose from your files", function () {
       showModalSkeleton("chrome_open", { surface: "attachments" });
       action("chrome_open", { surface: "attachments" });
     }]
    ].forEach(function (pair) {
      var b = document.createElement("button");
      b.type = "button"; b.className = "astral-attach-menu-item"; b.textContent = pair[0];
      b.addEventListener("click", function () { closeAttachMenu(); pair[1](); });
      attachMenu.appendChild(b);
    });
    (attachBtn.parentNode || document.body).appendChild(attachMenu);
  }
  if (attachBtn && attachInput) {
    attachBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      if (attachMenu) closeAttachMenu(); else openAttachMenu();
    });
    document.addEventListener("click", function (e) {
      if (attachMenu && !attachMenu.contains(e.target) && e.target !== attachBtn) closeAttachMenu();
    });
  }
  // Attach an EXISTING file from the library modal — stage a ready chip with no
  // re-upload, then close the modal (US3).
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest(".astral-attach-existing");
    if (!btn) return;
    var aid = btn.getAttribute("data-attachment-id");
    if (!aid) return;
    if (stagedAttachments.length >= MAX_ATTACHMENTS) {
      setStatus("You can attach up to " + MAX_ATTACHMENTS + " files per message."); return;
    }
    var dup = stagedAttachments.some(function (a) { return a.attachment_id === aid; });
    if (!dup) {
      stagedAttachments.push({ uid: ++attachSeq, attachment_id: aid,
        filename: btn.getAttribute("data-filename") || "file",
        category: btn.getAttribute("data-category") || "file",
        state: "ready", note: "" });
      renderAttachments();
    }
    if (typeof setModal === "function") setModal("");
  });
  // Remove-chip delegation.
  if (attachEl) {
    attachEl.addEventListener("click", function (e) {
      var rm = e.target.closest && e.target.closest("[data-remove-uid]");
      if (rm) { removeStaged(parseInt(rm.getAttribute("data-remove-uid"), 10)); }
    });
  }
  // File selection (the hidden input carries class astral-file-upload).
  document.addEventListener("change", function (e) {
    if (!(e.target.classList && e.target.classList.contains("astral-file-upload"))) return;
    var files = e.target.files ? Array.prototype.slice.call(e.target.files) : [];
    if (!files.length) return;
    var room = MAX_ATTACHMENTS - stagedAttachments.length;
    if (room <= 0) { setStatus("You can attach up to " + MAX_ATTACHMENTS + " files per message."); e.target.value = ""; return; }
    if (files.length > room) { setStatus("Only " + room + " more file(s) can be attached to this message."); files = files.slice(0, room); }
    files.forEach(uploadStagedFile);
    e.target.value = "";  // allow re-selecting the same file later
  });

  // ---- 055 cross-device continuity: background-run arming + task chips ----
  // The composer toggle next to the paperclip arms async_mode for the NEXT
  // send only; sendChat reads bgArmed via hoisting (same contract as the
  // attachment helpers above it) and disarms after the message goes out.
  var bgBtn = document.getElementById("astral-bg-btn");
  var bgArmed = false;
  function setBgArmed(on) {
    bgArmed = !!on;
    if (!bgBtn) return;
    bgBtn.setAttribute("aria-pressed", bgArmed ? "true" : "false");
    // Armed look via the runtime theme tokens — this file styles its own
    // dynamic chrome inline (see showToast/openChromePop).
    bgBtn.style.cssText = bgArmed
      ? "color:rgb(var(--astral-primary));border-color:rgb(var(--astral-primary) / .7);background:rgb(var(--astral-primary) / .15);"
      : "";
  }
  if (bgBtn) bgBtn.addEventListener("click", function () { setBgArmed(!bgArmed); });

  // One slim chip per running background task (keyed by task_id, cleared by
  // its task_completed). Lives at the top of the composer so it survives chat
  // switches; tapping a chip opens the task's chat.
  var bgTaskChips = {};  // task_id → chip element
  var bgTaskDone = {};   // task_id → true (dedupes watcher + fan-out copies)
  var bgTaskHost = null;
  function bgTaskHostEl() {
    if (!bgTaskHost && form) {
      bgTaskHost = document.createElement("div");
      bgTaskHost.id = "astral-bgtasks";
      bgTaskHost.style.cssText = "display:none;flex-wrap:wrap;gap:6px;";
      form.insertBefore(bgTaskHost, form.firstChild);
    }
    return bgTaskHost;
  }
  function syncBgTaskHost() {
    if (bgTaskHost) bgTaskHost.style.display = bgTaskHost.children.length ? "flex" : "none";
  }
  function addTaskChip(taskId, chatId, title) {
    if (!taskId || bgTaskChips[taskId] || bgTaskDone[taskId]) return;
    var host = bgTaskHostEl();
    if (!host) return;
    var chip = document.createElement("button");
    chip.type = "button";
    chip.className = "astral-chip";
    chip.style.cursor = "pointer";
    chip.title = "Open the chat running this task";
    var dot = document.createElement("span");
    dot.style.cssText = "width:7px;height:7px;border-radius:9999px;background:rgb(var(--astral-primary));flex:none;";
    chip.appendChild(dot);
    var label = document.createElement("span");
    label.className = "astral-chip-name";
    label.textContent = "Background task running" + (title ? " — " + title : "…");
    chip.appendChild(label);
    if (chatId) chip.addEventListener("click", function () {
      if (chatId !== activeChatId) action("load_chat", { chat_id: chatId });
      closeHistoryOverlay();
    });
    host.appendChild(chip);
    bgTaskChips[taskId] = chip;
    syncBgTaskHost();
  }
  function removeTaskChip(taskId) {
    var chip = bgTaskChips[taskId];
    if (chip && chip.parentNode) chip.parentNode.removeChild(chip);
    delete bgTaskChips[taskId];
    syncBgTaskHost();
    // Don't leave the dispatch-time status text stranded once nothing runs.
    var any = false;
    for (var k in bgTaskChips) { any = true; break; }
    if (!any && statusEl && statusEl.textContent === "Running in background…") setStatus("");
  }

  // Chrome runtime: settings menu, modal surfaces, generic [data-ui-action]
  // delegation, and the tour step-runner. Server renders all chrome HTML
  // (webrender/chrome/); this block is plumbing only.
  var modalRoot = document.getElementById("astral-modal");
  var modalReturnFocus = null;

  // ---- chrome_open perceived latency (feature 052): a local skeleton fills
  // the modal instantly; chrome_render replaces it via setModal. If nothing
  // arrives within the timeout, a retry card re-sends the same chrome_open
  // instead of leaving an infinite shimmer. Focus is NOT moved here so
  // setModal still captures the real return-focus element when it lands.
  var MODAL_SKELETON_TIMEOUT_MS = 6000;
  var modalSkeletonTimer = null;
  var modalSkeletonRequest = null;
  function clearModalSkeletonTimer() {
    if (modalSkeletonTimer) { clearTimeout(modalSkeletonTimer); modalSkeletonTimer = null; }
  }
  function modalShellHtml(bodyHtml) {
    return '<div class="astral-modal-backdrop fixed inset-0 z-50 bg-black/60 backdrop-blur-sm '
      + 'flex items-start justify-center overflow-y-auto py-10">'
      + '<div class="astral-modal-card relative bg-astral-surface border border-white/10 rounded-xl '
      + 'shadow-2xl w-full max-w-3xl mx-4 my-auto" role="dialog" aria-modal="true" tabindex="-1">'
      + '<div class="px-5 py-4 space-y-4">' + bodyHtml + "</div></div></div>";
  }
  function showModalSkeleton(act, payload) {
    if (!modalRoot) return;
    clearModalSkeletonTimer();
    modalSkeletonRequest = { action: act, payload: payload || {} };
    modalRoot.innerHTML = modalShellHtml(
      '<div class="astral-skeleton" role="status" aria-busy="true" aria-live="polite">'
      + '<span class="sr-only">Loading…</span>'
      + '<div class="astral-skeleton-line h-3 w-1/3 mb-3"></div>'
      + '<div class="astral-skeleton-line h-20 w-full mb-3"></div>'
      + '<div class="astral-skeleton-line h-20 w-full mb-3"></div>'
      + '<div class="astral-skeleton-line h-3 w-1/2 mb-2"></div></div>');
    modalSkeletonTimer = setTimeout(showModalRetry, MODAL_SKELETON_TIMEOUT_MS);
  }
  function showModalRetry() {
    modalSkeletonTimer = null;
    if (!modalRoot || !modalSkeletonRequest) return;
    modalRoot.innerHTML = modalShellHtml(
      '<div class="text-sm text-astral-text" role="status">This is taking longer than expected.</div>'
      + '<div class="flex gap-2">'
      + '<button type="button" class="astral-modal-retry px-3 py-1.5 rounded-lg text-xs font-medium '
      + 'bg-astral-primary text-white">Retry</button>'
      + '<button type="button" class="astral-modal-close px-3 py-1.5 rounded-lg text-xs '
      + 'bg-white/5 border border-white/10 text-astral-text">Close</button></div>');
    var retry = modalRoot.querySelector(".astral-modal-retry");
    if (retry) retry.addEventListener("click", function () {
      var req = modalSkeletonRequest;
      showModalSkeleton(req.action, req.payload);
      action(req.action, req.payload);
    });
  }

  /** Replace the chrome modal content; empty html closes it (restores focus). */
  function setModal(htmlStr) {
    if (!modalRoot) return;
    clearModalSkeletonTimer();
    if (htmlStr) {
      modalReturnFocus = document.activeElement;
      modalRoot.innerHTML = htmlStr;
      processSideEffects(modalRoot);
      var card = modalRoot.querySelector(".astral-modal-card");
      if (card) card.focus();
      maybeStartTour();
    } else {
      modalRoot.innerHTML = "";
      if (modalReturnFocus && modalReturnFocus.focus) { try { modalReturnFocus.focus(); } catch (e) {} }
      modalReturnFocus = null;
    }
  }
  /** Feature 054: a modal whose card carries data-mandatory (the first-run
   *  provider-setup gate) refuses every dismissal affordance — ✕/backdrop/
   *  Escape all funnel here. The server closes it after a successful save;
   *  the dialog's "Sign out" link is the one escape hatch. */
  function modalIsMandatory() {
    return !!(modalRoot && modalRoot.querySelector && modalRoot.querySelector(".astral-modal-card[data-mandatory]"));
  }
  function closeModal() {
    if (!modalRoot || !modalRoot.innerHTML) return;
    if (modalIsMandatory()) return;
    setModal(""); action("chrome_close", {});
  }

  // ---- settings menu (static, server-rendered; WAI-ARIA menu pattern) ----
  function menuEl() { return document.getElementById("astral-settings-menu"); }
  function menuBtn() { return document.getElementById("astral-settings-btn"); }
  function menuItems() {
    var m = menuEl(); if (!m) return [];
    return Array.prototype.slice.call(m.querySelectorAll('[role="menuitem"]'));
  }
  function menuOpen() { var m = menuEl(); return !!(m && !m.hidden); }
  function setMenu(open, focusFirst) {
    var m = menuEl(), b = menuBtn(); if (!m || !b) return;
    m.hidden = !open;
    b.setAttribute("aria-expanded", open ? "true" : "false");
    if (open && focusFirst) { var items = menuItems(); if (items.length) items[0].focus(); }
    // Restoring focus to the gear is right for normal open/close, but mid-tour
    // it would arm the button's Enter/Space/ArrowDown handler — the next key
    // press would reopen the menu instead of advancing the tour.
    if (!open && !tourState) { try { b.focus(); } catch (e) {} }
  }
  function menuMove(delta, edge) {
    var items = menuItems(); if (!items.length) return;
    var idx = items.indexOf(document.activeElement);
    var next = edge != null ? edge : (idx < 0 ? 0 : (idx + delta + items.length) % items.length);
    items[next].focus();
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("#astral-settings-btn");
    if (btn) { setMenu(!menuOpen(), false); return; }
    // Tour-card clicks must not count as "outside" — the tour opens the menu
    // to spotlight in-menu targets, and Next would otherwise close it again.
    var inTour = e.target.closest && e.target.closest("#astral-tour-card");
    if (menuOpen() && !inTour && !(e.target.closest && e.target.closest("#astral-settings-menu"))) setMenu(false, false);
    // modal close affordances: X button or backdrop click
    if (e.target.closest && e.target.closest(".astral-modal-close")) { closeModal(); return; }
    var backdrop = e.target.classList && e.target.classList.contains("astral-modal-backdrop");
    if (backdrop) closeModal();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      if (tourState) { endTour("dismissed"); return; }
      if (menuOpen()) { setMenu(false, false); return; }
      if (modalRoot && modalRoot.innerHTML) { closeModal(); return; }
    }
    var b = menuBtn();
    if (document.activeElement === b && (e.key === "Enter" || e.key === " " || e.key === "ArrowDown")) {
      e.preventDefault(); setMenu(true, true); return;
    }
    if (!menuOpen()) return;
    var inMenu = e.target.closest && e.target.closest("#astral-settings-menu");
    if (!inMenu) return;
    if (e.key === "ArrowDown") { e.preventDefault(); menuMove(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); menuMove(-1); }
    else if (e.key === "Home") { e.preventDefault(); menuMove(0, 0); }
    else if (e.key === "End") { e.preventDefault(); menuMove(0, menuItems().length - 1); }
    else if (e.key === "Tab") { e.preventDefault(); menuMove(e.shiftKey ? -1 : 1); }
  });

  // ---- generic [data-ui-action] delegation (chrome surfaces + creation cards) ----
  function collectChromeFields(container) {
    var fields = {};
    if (!container) return fields;
    var els = container.querySelectorAll("input[name], select[name], textarea[name]");
    for (var i = 0; i < els.length; i++) {
      var el = els[i], name = el.getAttribute("name");
      if (el.type === "checkbox") fields[name] = el.checked;
      else if (el.type === "radio") { if (el.checked) fields[name] = el.value; }
      else if (el.type === "number") fields[name] = el.value === "" ? null : Number(el.value);
      else fields[name] = el.value;
    }
    return fields;
  }

  document.addEventListener("click", function (e) {
    var el = e.target.closest && e.target.closest("[data-ui-action]");
    if (!el) return;
    var act = el.getAttribute("data-ui-action");
    var payload = {};
    try { payload = JSON.parse(el.getAttribute("data-ui-payload") || "{}"); } catch (err) {}
    if (el.getAttribute("data-ui-collect") === "true") {
      payload.fields = collectChromeFields(el.closest("[data-ui-form]") || modalRoot);
    }
    // The timeline surface needs the active chat, which only the client knows
    // at click time (the static menu is rendered per shell).
    if (act === "chrome_open" && payload.surface === "workspace_timeline") {
      payload.params = payload.params || {};
      if (!payload.params.chat_id && activeChatId) payload.params.chat_id = activeChatId;
    }
    if (act === "chrome_open") { setMenu(false, false); showModalSkeleton(act, payload); }
    action(act, payload);
  });

  // Permission sections (Agents & permissions): the section master gates its
  // tool switches — on enables them all, off clears and disables them. The
  // server enforces the same rule on save; this just keeps the form honest.
  document.addEventListener("change", function (e) {
    var t = e.target;
    if (!(t.classList && t.classList.contains("astral-perm-master"))) return;
    var section = t.closest && t.closest("[data-perm-section]");
    if (!section) return;
    var on = t.checked;
    var tools = section.querySelectorAll(".astral-perm-tool");
    for (var i = 0; i < tools.length; i++) { tools[i].checked = on; tools[i].disabled = !on; }
    var body = section.querySelector(".astral-perm-tools");
    if (body) body.classList.toggle("opacity-50", !on);
  });

  // LLM provider picker (feature 054): the chrome modal is static HTML with no
  // reactive re-render, so toggle the endpoint field client-side when the
  // provider dropdown changes — show the free-form base_url input only for
  // "custom", otherwise show the (auto-set) preset endpoint caption. The
  // server still derives the URL for presets, so the hidden input is inert.
  document.addEventListener("change", function (e) {
    var t = e.target;
    if (!(t.classList && t.classList.contains("astral-llm-provider"))) return;
    var form = t.closest && t.closest("[data-ui-form]");
    var wrap = form && form.querySelector(".astral-llm-endpoint");
    if (!wrap) return;
    var map = {};
    try { map = JSON.parse(form.getAttribute("data-llm-endpoints") || "{}"); } catch (err) {}
    var preset = wrap.querySelector(".astral-llm-endpoint-preset");
    var custom = wrap.querySelector(".astral-llm-endpoint-custom");
    var urlEl = wrap.querySelector(".astral-llm-endpoint-url");
    var input = wrap.querySelector('input[name="base_url"]');
    if (t.value === "custom") {
      if (preset) preset.style.display = "none";
      if (custom) custom.style.display = "";
      if (input) { input.value = ""; input.focus(); }
    } else {
      if (custom) custom.style.display = "none";
      if (preset) preset.style.display = "";
      if (urlEl) urlEl.textContent = map[t.value] || "";
      if (input) input.value = "";  // preset URL is derived server-side
    }
  });

  // ---- tour runner (steps server-rendered into [data-tour-steps]; A10 skips) ----
  var tourState = null;
  function maybeStartTour() {
    var holder = modalRoot && modalRoot.querySelector("[data-tour-steps]");
    if (!holder) return;
    var steps = [];
    try { steps = JSON.parse(holder.getAttribute("data-tour-steps") || "[]"); } catch (e) { return; }
    if (!steps.length) return;
    setModal(""); // tour replaces the modal with its floating card
    action("chrome_close", {});
    tourState = { steps: steps, idx: 0 };
    action("chrome_tour_event", { event: "started" });
    showTourStep();
  }
  function tourTargetEl(step) {
    if (!step.target_key) return null;
    try { return document.querySelector('[data-tour-target="' + step.target_key + '"]'); } catch (e) { return null; }
  }
  function clearTourHighlight() {
    var hl = document.querySelectorAll(".astral-tour-highlight");
    for (var i = 0; i < hl.length; i++) hl[i].classList.remove("astral-tour-highlight");
    var card = document.getElementById("astral-tour-card");
    if (card) card.parentNode.removeChild(card);
  }
  function showTourStep() {
    if (!tourState) return;
    clearTourHighlight();
    var step = tourState.steps[tourState.idx];
    var target = tourTargetEl(step);
    var skippedNote = "";
    if (step.target_kind === "static" && step.target_key && !target) {
      // A10: target belongs to chrome that isn't built yet — note + no highlight.
      skippedNote = '<div class="text-xs text-astral-muted italic mt-1">(this step’s target isn’t available yet)</div>';
    }
    // In-menu targets need the popover open (and laid out — scrollIntoView is
    // a no-op while it is hidden) BEFORE the highlight; any other step closes
    // it again so it doesn't cover the topbar/canvas highlights (Back
    // navigation, the no-target intro/outro cards).
    if (target && (target.id === "astral-settings-menu" || (target.closest && target.closest("#astral-settings-menu")))) setMenu(true, false);
    else if (menuOpen()) setMenu(false, false);
    if (target) {
      target.classList.add("astral-tour-highlight");
      if (target.scrollIntoView) target.scrollIntoView({ block: "nearest" });
    }
    var card = document.createElement("div");
    card.id = "astral-tour-card";
    card.className = "fixed bottom-6 left-1/2 -translate-x-1/2 z-[70] w-[360px] max-w-[90vw] " +
      "bg-astral-surface border border-white/10 rounded-xl shadow-2xl p-4";
    var last = tourState.idx === tourState.steps.length - 1;
    card.innerHTML =
      '<div class="text-xs text-astral-muted mb-1">Step ' + (tourState.idx + 1) + " of " + tourState.steps.length + "</div>" +
      '<div class="text-sm font-semibold text-astral-text mb-1" id="astral-tour-title"></div>' +
      '<div class="text-sm text-astral-text/80" id="astral-tour-body"></div>' + skippedNote +
      '<div class="flex justify-between items-center mt-3">' +
      '<button type="button" class="astral-tour-skip text-xs text-astral-muted hover:text-astral-text">Skip tour</button>' +
      '<div class="flex gap-2">' +
      (tourState.idx > 0 ? '<button type="button" class="astral-tour-back px-3 py-1.5 rounded-lg text-xs bg-white/5 border border-white/10 text-astral-text">Back</button>' : "") +
      '<button type="button" class="astral-tour-next px-3 py-1.5 rounded-lg text-xs font-medium bg-astral-primary text-white">' + (last ? "Finish" : "Next") + "</button>" +
      "</div></div>";
    document.body.appendChild(card);
    // server step content is text — set via textContent to stay inert
    card.querySelector("#astral-tour-title").textContent = step.title || "";
    card.querySelector("#astral-tour-body").textContent = step.body || "";
    var next = card.querySelector(".astral-tour-next");
    next.addEventListener("click", function () {
      if (last) { endTour("completed"); }
      else { tourState.idx++; showTourStep(); }
    });
    var back = card.querySelector(".astral-tour-back");
    if (back) back.addEventListener("click", function () { tourState.idx--; showTourStep(); });
    card.querySelector(".astral-tour-skip").addEventListener("click", function () { endTour("skipped"); });
    // Each step rebuilds the card, dropping focus to <body>; put it on Next so
    // Enter keeps advancing for keyboard users.
    try { next.focus(); } catch (e) {}
  }
  function endTour(outcome) {
    var wasRunning = !!tourState;
    tourState = null; // before setMenu so the gear regains focus at tour end
    clearTourHighlight();
    setMenu(false, false);
    if (wasRunning) action("chrome_tour_event", { event: outcome });
  }

  // ---- connection lifecycle ----
  function connect() {
    ws = new WebSocket(WS_URL);
    ws.onopen = function () {
      attempts = 0; authRetried = false; setStatus("");
      send({ type: "register_ui", token: token, capabilities: ["render", "stream"],
             session_id: "ui-" + Date.now(), device: detectDeviceCapabilities(),
             resumed: firstConnect ? serverResumed : true });
      firstConnect = false;
      action("get_history", {});
      // Re-attach to still-running background tasks: watch_task re-registers
      // this socket as a watcher and answers task_completed immediately when
      // the task finished while the socket was down.
      for (var tid in bgTaskChips) action("watch_task", { task_id: tid });
      var qp = new URLSearchParams(location.search).get("chat");
      if (qp) setTimeout(function () { action("load_chat", { chat_id: qp }); }, 500);
    };
    ws.onmessage = onMessage;
    ws.onerror = function () { try { ws.close(); } catch (e) {} };
    ws.onclose = function () {
      setStatus("Disconnected"); attempts++;
      hideSkeleton(); // the in-flight turn died with the socket
      // Refresh the session token BEFORE reconnecting so a register_ui after
      // the access-token TTL recovers silently instead of dead-ending. First
      // connect uses the shell-injected token directly.
      if (attempts <= 10) setTimeout(function () {
        refreshToken(false, function () { connect(); });
      }, 3000);
    };
  }
  connect();

  // Warm the lazy Plotly bundle once the boot work has settled so the first
  // chart-bearing turn is usually already loaded.
  function idlePrefetchPlotly() { ensurePlotly(null); }
  if (window.requestIdleCallback) window.requestIdleCallback(idlePrefetchPlotly, { timeout: 5000 });
  else setTimeout(idlePrefetchPlotly, 2500);
})();

/* Feature 040 (US5): slash-command typeahead. Discovery only — the server
   rewrites a "/command" into a normal prompt; nothing here invokes a tool. The
   curated list mirrors orchestrator/slash_commands.COMMANDS. */
(function () {
  var COMMANDS = [
    { name: "/help", desc: "show available commands" },
    { name: "/agents", desc: "list your enabled agents" },
    { name: "/summarize", desc: "summarize a link or text" },
    { name: "/research", desc: "research + cited brief" },
    { name: "/weather", desc: "weather + forecast" },
    { name: "/download", desc: "get the Windows desktop app" }
  ];
  var input = document.getElementById("astral-input");
  var menu = document.getElementById("astral-slash-menu");
  if (!input || !menu) return;

  function hide() { menu.classList.add("hidden"); menu.innerHTML = ""; }

  function render(matches) {
    if (!matches.length) { hide(); return; }
    menu.innerHTML = "";
    matches.forEach(function (c) {
      var item = document.createElement("button");
      item.type = "button";
      item.className = "astral-slash-item";
      item.setAttribute("role", "option");
      var n = document.createElement("span");
      n.className = "astral-slash-name";
      n.textContent = c.name;
      var d = document.createElement("span");
      d.className = "astral-slash-desc";
      d.textContent = c.desc;
      item.appendChild(n);
      item.appendChild(d);
      // mousedown (not click) fires before the input blur that would hide us.
      item.addEventListener("mousedown", function (e) {
        e.preventDefault();
        input.value = c.name + " ";
        hide();
        input.focus();
      });
      menu.appendChild(item);
    });
    menu.classList.remove("hidden");
  }

  function update() {
    var trimmed = (input.value || "").replace(/^\s+/, "");
    // Only while typing the command NAME: a leading "/" and no space yet.
    if (trimmed.charAt(0) !== "/" || trimmed.indexOf(" ") !== -1) { hide(); return; }
    var prefix = trimmed.toLowerCase();
    render(COMMANDS.filter(function (c) { return c.name.indexOf(prefix) === 0; }));
  }

  input.addEventListener("input", update);
  input.addEventListener("blur", function () { setTimeout(hide, 120); });
  input.addEventListener("keydown", function (e) { if (e.key === "Escape") hide(); });
})();
