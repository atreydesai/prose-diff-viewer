/* prose-diff-viewer client */
"use strict";

const $ = (id) => document.getElementById(id);
const docSel = $("doc-select"), baseSel = $("base-select"), cmpSel = $("compare-select");

let manifest = null;
let changes = [];
let focusIdx = -1;

async function api(path) {
  const r = await fetch(path);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

function currentDoc() {
  return manifest.documents.find((d) => d.id === docSel.value);
}

function fillVersions() {
  const doc = currentDoc();
  if (!doc) return;
  for (const sel of [baseSel, cmpSel]) {
    sel.innerHTML = "";
    for (const v of doc.versions) {
      const o = document.createElement("option");
      o.value = v.id;
      o.textContent = v.label + (v.detail ? ` — ${v.detail}` : "");
      sel.appendChild(o);
    }
  }
  // default: first version vs latest
  baseSel.selectedIndex = 0;
  cmpSel.selectedIndex = doc.versions.length - 1;
}

function stepPair(delta) {
  const n = currentDoc().versions.length;
  const b = baseSel.selectedIndex + delta, c = cmpSel.selectedIndex + delta;
  if (b < 0 || c < 0 || b >= n || c >= n) return;
  baseSel.selectedIndex = b;
  cmpSel.selectedIndex = c;
  loadDiff();
}

function setUrl() {
  const p = new URLSearchParams({ doc: docSel.value, base: baseSel.value, compare: cmpSel.value });
  history.replaceState(null, "", "?" + p.toString());
}

async function loadDiff() {
  const docEl = $("doc");
  docEl.innerHTML = '<p class="placeholder">Building diff…</p>';
  try {
    const q = new URLSearchParams({ doc: docSel.value, base: baseSel.value, compare: cmpSel.value });
    const r = await api("/api/diff?" + q);
    docEl.innerHTML = r.html;
    changes = r.changes;
    focusIdx = -1;
    $("stat-added").textContent = r.words_added;
    $("stat-removed").textContent = r.words_removed;
    $("stats").hidden = false;
    renderChangeList();
    setUrl();
  } catch (e) {
    docEl.innerHTML = `<p class="placeholder">Error: ${e.message}</p>`;
  }
}

function renderChangeList() {
  const list = $("change-list");
  list.innerHTML = "";
  $("changes-head").hidden = false;
  $("change-count").textContent = changes.length;
  $("change-nav").hidden = changes.length === 0;
  $("change-pos").textContent = changes.length ? `– / ${changes.length}` : "";
  changes.forEach((c, i) => {
    const li = document.createElement("li");
    li.innerHTML = `<span class="k ${c.kind}">${c.kind}</span>${escapeHtml(c.excerpt)}`;
    li.title = c.excerpt;
    li.onclick = () => focusChange(i);
    list.appendChild(li);
  });
}

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]));
}

function focusChange(i) {
  if (!changes.length) return;
  focusIdx = ((i % changes.length) + changes.length) % changes.length;
  document.querySelectorAll(".change.focus").forEach((el) => el.classList.remove("focus"));
  document.querySelectorAll("#change-list li.active").forEach((el) => el.classList.remove("active"));
  const target = document.getElementById(changes[focusIdx].id);
  if (target) {
    target.classList.add("focus");
    target.scrollIntoView({ block: "center" });
  }
  const li = $("change-list").children[focusIdx];
  if (li) {
    li.classList.add("active");
    li.scrollIntoView({ block: "nearest" });
  }
  $("change-pos").textContent = `${focusIdx + 1} / ${changes.length}`;
}

async function init() {
  manifest = await api("/api/manifest");
  docSel.innerHTML = "";
  for (const d of manifest.documents) {
    const o = document.createElement("option");
    o.value = d.id;
    o.textContent = `${d.title} (${d.source})`;
    docSel.appendChild(o);
  }
  if (!manifest.documents.length) {
    $("doc").innerHTML = '<p class="placeholder">No versioned documents found in this book directory.</p>';
    return;
  }

  // restore deep link ?doc=..&base=..&compare=..
  const p = new URLSearchParams(location.search);
  if (p.get("doc") && manifest.documents.some((d) => d.id === p.get("doc"))) {
    docSel.value = p.get("doc");
  }
  fillVersions();
  for (const [sel, key] of [[baseSel, "base"], [cmpSel, "compare"]]) {
    const want = p.get(key);
    if (want && [...sel.options].some((o) => o.value === want)) sel.value = want;
  }

  docSel.onchange = () => { fillVersions(); loadDiff(); };
  baseSel.onchange = loadDiff;
  cmpSel.onchange = loadDiff;
  $("generate").onclick = loadDiff;
  $("prev-pair").onclick = () => stepPair(-1);
  $("next-pair").onclick = () => stepPair(1);
  $("prev-change").onclick = () => focusChange(focusIdx - 1);
  $("next-change").onclick = () => focusChange(focusIdx + 1);
  $("clean-read").onchange = (e) => document.body.classList.toggle("clean-read", e.target.checked);
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "SELECT" || e.target.tagName === "INPUT") return;
    if (e.key === "n") focusChange(focusIdx + 1);
    if (e.key === "p") focusChange(focusIdx - 1);
  });

  loadDiff();
}

init().catch((e) => {
  $("doc").innerHTML = `<p class="placeholder">Failed to load: ${e.message}</p>`;
});
