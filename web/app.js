/* Convergence Monitor — static dashboard.
 *
 * Dependency-free. On load, fetches ./data/alert.json (an alert card matching
 * the AlertRecord schema) and ./data/history.json (a small array of
 * {date, convergence_score, confidence} points) and renders them.
 *
 * No build step, no framework. All DOM construction uses textContent and
 * createElement, so external strings (titles, terms, URLs) are never injected
 * as HTML.
 */
(function () {
  "use strict";

  var GAUGE_RADIUS = 52;
  var GAUGE_CIRCUMFERENCE = 2 * Math.PI * GAUGE_RADIUS;
  var SCORE_MAX = 10;

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    Promise.all([
      fetchJson("./data/alert.json"),
      fetchJson("./data/history.json").catch(function () {
        // History is optional; the rest of the page should still render.
        return null;
      }),
    ])
      .then(function (results) {
        render(results[0], results[1]);
      })
      .catch(function (err) {
        showError(err);
      });
  }

  function fetchJson(url) {
    return fetch(url, { cache: "no-store" }).then(function (resp) {
      if (!resp.ok) {
        throw new Error("Failed to load " + url + " (HTTP " + resp.status + ")");
      }
      return resp.json();
    });
  }

  function showError(err) {
    var status = byId("status-line");
    status.textContent =
      "Could not load dashboard data: " +
      (err && err.message ? err.message : String(err)) +
      ". If you opened this file directly, serve it with a local web server " +
      "(see web/README.md).";
    status.classList.add("error");
    status.hidden = false;
    byId("dashboard").hidden = true;
  }

  function render(alert, history) {
    if (!alert || typeof alert !== "object") {
      showError(new Error("alert.json did not contain an object"));
      return;
    }

    renderHeader(alert);
    renderScore(alert);
    renderSummary(alert);
    renderSparkline(history);
    renderEvidence(alert.evidence);
    renderList("warnings-list", alert.warnings);
    renderList("limitations-list", alert.limitations);

    byId("status-line").hidden = true;
    byId("dashboard").hidden = false;
  }

  function renderHeader(alert) {
    if (alert.scenario_name) {
      setText("scenario-name", alert.scenario_name);
      document.title = alert.scenario_name + " — Convergence Monitor";
    }
  }

  function renderScore(alert) {
    var score = toNumber(alert.convergence_score);
    var band = scoreBand(score);

    setText("score-number", score === null ? "—" : formatScore(score));

    var bandEl = byId("score-band");
    bandEl.textContent = band || "—";
    setBandClass(bandEl, band);

    var confidence = normalizeLevel(alert.confidence);
    var confEl = byId("confidence-badge");
    confEl.textContent = confidence || "—";
    setBandClass(confEl, confidence);

    setText("document-count", formatCount(alert.document_count));
    setText("categories-active", formatCount(alert.source_categories_active));
    setText(
      "window-days",
      alert.window_days != null ? alert.window_days + " days" : "—"
    );
    setText("generated-at", formatDate(alert.generated_at));

    // Gauge arc.
    var gauge = byId("gauge-value");
    gauge.setAttribute("stroke-dasharray", GAUGE_CIRCUMFERENCE.toFixed(2));
    if (score === null) {
      gauge.setAttribute("stroke-dashoffset", GAUGE_CIRCUMFERENCE.toFixed(2));
    } else {
      var fraction = clamp(score / SCORE_MAX, 0, 1);
      var offset = GAUGE_CIRCUMFERENCE * (1 - fraction);
      gauge.setAttribute("stroke-dashoffset", offset.toFixed(2));
    }
  }

  function renderSummary(alert) {
    setText("summary", alert.summary || "No summary provided.");
  }

  function renderEvidence(evidence) {
    var body = byId("evidence-body");
    body.textContent = "";

    if (!Array.isArray(evidence) || evidence.length === 0) {
      var tr = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = 7;
      td.className = "muted";
      td.textContent = "No evidence documents in this alert.";
      tr.appendChild(td);
      body.appendChild(tr);
      return;
    }

    evidence.forEach(function (item, index) {
      var tr = document.createElement("tr");

      tr.appendChild(cell(String(index + 1), "rank-cell"));

      // Title
      tr.appendChild(cell(item.title || "(untitled)"));

      // Source: name + category
      var sourceTd = document.createElement("td");
      var nameDiv = document.createElement("div");
      nameDiv.textContent = item.source_name || item.source_id || "—";
      sourceTd.appendChild(nameDiv);
      if (item.source_category) {
        var catDiv = document.createElement("div");
        catDiv.className = "muted";
        catDiv.style.margin = "0";
        catDiv.textContent = humanize(item.source_category);
        sourceTd.appendChild(catDiv);
      }
      tr.appendChild(sourceTd);

      // Relevance
      var relTd = document.createElement("td");
      var relSpan = document.createElement("span");
      var rel = (item.relevance || "").toString();
      relSpan.className = "rel-tag rel-" + (rel || "unknown");
      relSpan.textContent = rel || "—";
      relTd.appendChild(relSpan);
      tr.appendChild(relTd);

      // Matched terms
      var termsTd = document.createElement("td");
      var terms = Array.isArray(item.matched_terms) ? item.matched_terms : [];
      if (terms.length === 0) {
        termsTd.textContent = "—";
      } else {
        var termsWrap = document.createElement("div");
        termsWrap.className = "terms";
        terms.forEach(function (term) {
          var span = document.createElement("span");
          span.className = "term";
          span.textContent = String(term);
          termsWrap.appendChild(span);
        });
        termsTd.appendChild(termsWrap);
      }
      tr.appendChild(termsTd);

      // Published date
      tr.appendChild(cell(formatDate(item.published_at), "nowrap"));

      // Link
      var linkTd = document.createElement("td");
      if (item.url) {
        var a = document.createElement("a");
        a.href = item.url;
        a.textContent = "View";
        a.rel = "noopener noreferrer";
        a.target = "_blank";
        linkTd.appendChild(a);
      } else {
        linkTd.textContent = "—";
      }
      tr.appendChild(linkTd);

      body.appendChild(tr);
    });
  }

  function renderList(id, items) {
    var ul = byId(id);
    ul.textContent = "";
    var values = Array.isArray(items) ? items : [];
    if (values.length === 0) {
      var li = document.createElement("li");
      li.textContent = "None reported.";
      ul.appendChild(li);
      return;
    }
    values.forEach(function (value) {
      var li = document.createElement("li");
      li.textContent = String(value); // verbatim
      ul.appendChild(li);
    });
  }

  function renderSparkline(history) {
    var container = byId("sparkline");
    var empty = byId("sparkline-empty");
    container.textContent = "";

    var points = Array.isArray(history)
      ? history
          .filter(function (p) {
            return p && toNumber(p.convergence_score) !== null;
          })
          .map(function (p) {
            return {
              date: p.date,
              score: toNumber(p.convergence_score),
              confidence: normalizeLevel(p.confidence),
            };
          })
      : [];

    if (points.length === 0) {
      empty.hidden = false;
      return;
    }
    empty.hidden = true;

    var W = 720;
    var H = 160;
    var pad = { top: 16, right: 16, bottom: 28, left: 32 };
    var innerW = W - pad.left - pad.right;
    var innerH = H - pad.top - pad.bottom;

    var n = points.length;
    function x(i) {
      return n === 1 ? pad.left + innerW / 2 : pad.left + (innerW * i) / (n - 1);
    }
    function y(score) {
      return pad.top + innerH * (1 - clamp(score / SCORE_MAX, 0, 1));
    }

    var svgNs = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(svgNs, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

    // Gridlines + y labels at 0, 5, 10.
    [0, 5, 10].forEach(function (val) {
      var gy = y(val);
      var line = document.createElementNS(svgNs, "line");
      line.setAttribute("x1", pad.left);
      line.setAttribute("x2", W - pad.right);
      line.setAttribute("y1", gy);
      line.setAttribute("y2", gy);
      line.setAttribute("stroke", "#e3e7ee");
      line.setAttribute("stroke-width", "1");
      svg.appendChild(line);

      var label = document.createElementNS(svgNs, "text");
      label.setAttribute("x", pad.left - 6);
      label.setAttribute("y", gy + 4);
      label.setAttribute("text-anchor", "end");
      label.setAttribute("font-size", "10");
      label.setAttribute("fill", "#8a93a3");
      label.textContent = String(val);
      svg.appendChild(label);
    });

    // Line path.
    var d = "";
    points.forEach(function (p, i) {
      d += (i === 0 ? "M" : "L") + x(i).toFixed(1) + " " + y(p.score).toFixed(1) + " ";
    });
    var path = document.createElementNS(svgNs, "path");
    path.setAttribute("d", d.trim());
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "#1f3a5f");
    path.setAttribute("stroke-width", "2");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("stroke-linecap", "round");
    svg.appendChild(path);

    // Point markers + accessible titles.
    points.forEach(function (p, i) {
      var c = document.createElementNS(svgNs, "circle");
      c.setAttribute("cx", x(i).toFixed(1));
      c.setAttribute("cy", y(p.score).toFixed(1));
      c.setAttribute("r", "3");
      c.setAttribute("fill", "#1f3a5f");
      var title = document.createElementNS(svgNs, "title");
      title.textContent =
        (p.date || "point " + (i + 1)) +
        ": " +
        formatScore(p.score) +
        (p.confidence ? " (" + p.confidence + ")" : "");
      c.appendChild(title);
      svg.appendChild(c);

      // First and last x-axis date labels only (keep it clean).
      if (i === 0 || i === n - 1) {
        var t = document.createElementNS(svgNs, "text");
        t.setAttribute("x", x(i).toFixed(1));
        t.setAttribute("y", H - 8);
        t.setAttribute("text-anchor", i === 0 ? "start" : "end");
        t.setAttribute("font-size", "10");
        t.setAttribute("fill", "#8a93a3");
        t.textContent = p.date || "";
        svg.appendChild(t);
      }
    });

    container.appendChild(svg);
  }

  /* ---------- helpers ---------- */

  function scoreBand(score) {
    if (score === null) return "";
    if (score >= 7.0) return "high";
    if (score >= 3.0) return "medium";
    return "low";
  }

  function setBandClass(el, level) {
    el.className = el.className.replace(/\b(band|badge)\b ?(low|medium|high)?/g, "").trim();
    var base = el.id === "confidence-badge" ? "badge" : "band";
    el.className = base + (level ? " " + level : "");
  }

  function normalizeLevel(value) {
    if (typeof value !== "string") return "";
    var v = value.trim().toLowerCase();
    return v === "low" || v === "medium" || v === "high" ? v : v;
  }

  function toNumber(value) {
    if (typeof value === "number" && isFinite(value)) return value;
    if (typeof value === "string" && value.trim() !== "") {
      var n = Number(value);
      if (isFinite(n)) return n;
    }
    return null;
  }

  function formatScore(score) {
    // One decimal place, matching the documented 0–10 band precision.
    return (Math.round(score * 10) / 10).toFixed(1);
  }

  function formatCount(value) {
    return value == null ? "—" : String(value);
  }

  function formatDate(value) {
    if (!value) return "—";
    var d = new Date(value);
    if (isNaN(d.getTime())) return String(value);
    var months = [
      "Jan", "Feb", "Mar", "Apr", "May", "Jun",
      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    return (
      months[d.getUTCMonth()] +
      " " +
      d.getUTCDate() +
      ", " +
      d.getUTCFullYear()
    );
  }

  function humanize(value) {
    return String(value).replace(/_/g, " ");
  }

  function clamp(v, lo, hi) {
    return Math.max(lo, Math.min(hi, v));
  }

  function cell(text, className) {
    var td = document.createElement("td");
    if (className) td.className = className;
    td.textContent = text;
    return td;
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function setText(id, text) {
    byId(id).textContent = text;
  }
})();
