// Page code: picture, text reader (Tesseract.js), form, saved list. Cleaning the photo, finding the
// details and writing vCard/CSV is done in Python (card.py) running in Pyodide.
const $ = (id) => document.getElementById(id);
const STORE = "bcs-contacts";

let py = null, cardPy = null, fields = [];
let ocr = null;
let source = null;        // the picture as a canvas, before cleaning
let cleaned = null;       // the cleaned picture as a canvas
let busy = false;
let editing = -1;         // index of the saved contact being edited, or -1 for a new one
let contacts = loadContacts();

// ---------- start-up ----------
async function start() {
  try {
    py = await loadPyodide({ indexURL: new URL("pyodide/", location.href).href });
    $("loadText").textContent = "Loading NumPy…";
    await py.loadPackage("numpy");
    $("loadText").textContent = "Loading the card reader…";
    const code = await fetch("card.py").then((r) => { if (!r.ok) throw new Error("card.py missing"); return r.text(); });
    py.FS.writeFile("/home/pyodide/card.py", code);
    py.runPython("import card");
    cardPy = py.pyimport("card");
    fields = JSON.parse(cardPy.fields_json());
    buildForm();
    $("loadText").textContent = "Loading the text reader…";
    ocr = await Tesseract.createWorker("eng", 1, {
      workerPath: new URL("tesseract/worker.min.js", location.href).href,
      corePath: new URL("tesseract/core/", location.href).href,
      langPath: new URL("tesseract/lang/", location.href).href,
      workerBlobURL: false,
      logger: (m) => progress(m),
    });
    // Page mode 3 = find the text blocks on the card by itself (the default, 6, expects one block and drops big names).
    await ocr.setParameters({ tessedit_pageseg_mode: "3", preserve_interword_spaces: "1", user_defined_dpi: "300" });
    $("loading").hidden = true;
    document.querySelectorAll("button, input").forEach((b) => { b.disabled = false; });
    $("rotate").disabled = $("rescan").disabled = true;
    setFormEnabled(false);
    renderList();
    const sample = new URLSearchParams(location.search).get("sample");
    if (sample) loadFrom(`samples/${sample}`);
  } catch (e) {
    console.error(e);
    $("loading").classList.add("error");
    $("loadText").textContent = "Sorry, the app could not start: " + e.message;
    document.querySelector("#loading .spinner").style.display = "none";
  }
}

// ---------- pictures ----------
function loadFrom(src) {
  const img = new Image();
  img.onload = () => useImage(img);
  img.onerror = () => say("That picture could not be opened. Try a JPG or PNG.", "warn");
  img.src = src;
}

function loadFile(file) {
  if (!file || !file.type.startsWith("image/")) { say("Please choose a picture (JPG, PNG or HEIC from a phone).", "warn"); return; }
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => { useImage(img); URL.revokeObjectURL(url); };
  img.onerror = () => say("That picture could not be opened in this browser. Try a JPG or PNG.", "warn");
  img.src = url;
}

function useImage(img) {
  // Card text reads best at about 1,600 pixels wide: enlarge small pictures, shrink huge ones.
  const w0 = img.naturalWidth, h0 = img.naturalHeight;
  const scale = Math.min(2.5, 1600 / Math.max(w0, h0) * (w0 >= h0 ? 1 : 1.2));
  const c = document.createElement("canvas");
  c.width = Math.round(w0 * scale); c.height = Math.round(h0 * scale);
  const g = c.getContext("2d");
  g.imageSmoothingQuality = "high";
  g.drawImage(img, 0, 0, c.width, c.height);
  source = c;
  scan();
}

function rotate() {
  if (!source) return;
  const c = document.createElement("canvas");
  c.width = source.height; c.height = source.width;
  const g = c.getContext("2d");
  g.translate(c.width, 0); g.rotate(Math.PI / 2);
  g.drawImage(source, 0, 0);
  source = c;
  scan();
}

function cleanPicture(canvas) {
  const g = canvas.getContext("2d");
  const { data } = g.getImageData(0, 0, canvas.width, canvas.height);
  const res = cardPy.clean_image(data, canvas.width, canvas.height);
  const [bytes, w, h] = res.toJs();
  res.destroy();
  const out = document.createElement("canvas");
  out.width = w; out.height = h;
  const og = out.getContext("2d");
  const im = og.createImageData(w, h);
  for (let i = 0, j = 0; i < bytes.length; i++, j += 4) {
    im.data[j] = im.data[j + 1] = im.data[j + 2] = bytes[i]; im.data[j + 3] = 255;
  }
  og.putImageData(im, 0, 0);
  return out;
}

function showPreview() {
  const pic = $("showClean").checked && cleaned ? cleaned : source;
  if (!pic) return;
  const pv = $("preview");
  pv.width = pic.width; pv.height = pic.height;
  pv.getContext("2d").drawImage(pic, 0, 0);
  $("drop").classList.add("has");
}

// ---------- reading ----------
function progress(m) {
  if (m.status === "recognizing text") {
    $("ocrFill").style.width = Math.round(m.progress * 100) + "%";
    $("ocrText").textContent = `Reading the card… ${Math.round(m.progress * 100)}%`;
  }
}

async function scan() {
  if (!source || busy) return;
  busy = true;
  setScanEnabled(false);
  say("");
  try {
    $("ocrBar").hidden = false;
    $("ocrFill").style.width = "0%";
    $("ocrText").textContent = "Cleaning up the photo (Python)…";
    showPreview();
    await new Promise((r) => setTimeout(r, 30));
    cleaned = $("cleanOn").checked ? cleanPicture(source) : null;
    showPreview();
    $("ocrText").textContent = "Reading the card…";
    const { data } = await ocr.recognize(cleaned || source, {}, { text: true, blocks: true });
    const lines = [];
    for (const b of data.blocks || []) for (const p of b.paragraphs || []) for (const l of p.lines || []) {
      const t = (l.text || "").trim();
      if (t) lines.push({ text: t, height: l.bbox.y1 - l.bbox.y0, conf: l.confidence });
    }
    $("raw").textContent = lines.map((l) => l.text).join("\n") || "(no text found)";
    const contact = JSON.parse(cardPy.parse_json(JSON.stringify(lines)));
    editing = -1;
    fillForm(contact, true);
    const found = ["name", "email", "mobile", "phone"].filter((k) => contact[k]).length;
    if (!lines.length) say("No text found. Try a sharper photo, more light, or press Turn if the card is sideways.", "warn");
    else if (!found) say("Couldn't find a name or number. Check the text below, or press Turn if the card is sideways.", "warn");
    else say("Check the details, then save.", "");
  } catch (e) {
    console.error(e);
    say("Something went wrong reading that card: " + e.message, "warn");
  } finally {
    $("ocrBar").hidden = true;
    busy = false;
    setScanEnabled(true);
  }
}

function setScanEnabled(on) {
  document.querySelectorAll(".sample, #camera, #upload, #rotate, #rescan").forEach((b) => { b.disabled = !on; });
  $("cameraBtn").classList.toggle("off", !on);
  $("uploadBtn").classList.toggle("off", !on);
  if (on && !source) $("rotate").disabled = $("rescan").disabled = true;
}

// ---------- the form ----------
function buildForm() {
  const f = $("form");
  f.innerHTML = "";
  const types = { email: "email", website: "url", mobile: "tel", phone: "tel", fax: "tel" };
  for (const { key, label } of fields) {
    const d = document.createElement("div");
    d.className = "field" + (["address", "notes"].includes(key) ? " full" : "");
    const id = "f-" + key;
    const input = key === "address" || key === "notes" ? document.createElement("textarea") : document.createElement("input");
    if (input.tagName === "INPUT") input.type = types[key] || "text";
    if (input.tagName === "TEXTAREA") input.rows = key === "address" ? 2 : 1;
    input.id = id; input.name = key;
    input.addEventListener("input", () => { input.classList.remove("found"); setFormEnabled(true); });
    const l = document.createElement("label");
    l.htmlFor = id; l.textContent = label;
    d.append(l, input);
    f.appendChild(d);
  }
}

function readForm() {
  const c = {};
  for (const { key } of fields) c[key] = $("f-" + key).value.trim();
  return c;
}

function fillForm(c, mark) {
  for (const { key } of fields) {
    const el = $("f-" + key);
    el.value = c[key] || "";
    el.classList.toggle("found", !!mark && !!c[key]);
  }
  $("checkHint").textContent = editing >= 0 ? "Editing a saved contact." : "Fix anything the reader got wrong.";
  setFormEnabled(true);
}

function setFormEnabled() {
  const c = fields.length ? readForm() : {};
  const any = Object.values(c).some(Boolean);
  $("save").disabled = $("saveVcf").disabled = $("clearForm").disabled = !any;
  $("save").textContent = editing >= 0 ? "💾 Update contact" : "💾 Save to my list";
}

function clearForm() {
  editing = -1;
  fillForm({}, false);
  $("checkHint").textContent = "Scan a card and the details appear here. Fix anything the reader got wrong.";
  say("");
}

function say(text, kind) {
  const m = $("saveMsg");
  m.textContent = text;
  m.className = "small msg" + (kind ? " " + kind : "");
}

// ---------- saving ----------
function loadContacts() {
  try { return JSON.parse(localStorage.getItem(STORE) || "[]"); } catch (e) { return []; }
}
function storeContacts() {
  try { localStorage.setItem(STORE, JSON.stringify(contacts)); }
  catch (e) { say("Couldn't save in this browser (private mode?). Use the download buttons instead.", "warn"); }
}

function saveContact() {
  const c = readForm();
  if (!Object.values(c).some(Boolean)) return;
  if (editing >= 0) {
    contacts[editing] = { ...contacts[editing], ...c };
    say(`Updated ${c.name || "the contact"}.`, "ok");
  } else {
    const dup = cardPy.duplicate_json(JSON.stringify(c), JSON.stringify(contacts));
    if (dup >= 0) {
      const o = contacts[dup];
      for (const k of Object.keys(c)) if (c[k]) o[k] = c[k];
      say(`${c.name || "This person"} was already in your list (same email or phone), so their details were updated.`, "warn");
    } else {
      contacts.unshift({ ...c, scanned: new Date().toISOString().slice(0, 10) });
      say(`Saved ${c.name || "the contact"}. Scan the next card!`, "ok");
    }
  }
  editing = -1;
  storeContacts();
  renderList();
  setFormEnabled();
}

function download(name, text, type) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type }));
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

const fileName = (c) => (c.name || c.company || "contact").replace(/[^\w\- ]+/g, "").trim().replace(/\s+/g, "-") || "contact";
const vcf = (list) => cardPy.vcards_json(JSON.stringify(list));

// ---------- the list ----------
function renderList() {
  const q = $("search").value.trim().toLowerCase();
  const tb = $("rows");
  tb.innerHTML = "";
  contacts.forEach((c, i) => {
    if (q && !Object.values(c).join(" ").toLowerCase().includes(q)) return;
    const tr = document.createElement("tr");
    const cell = (main, sub) => {
      const td = document.createElement("td");
      td.textContent = main || "";
      if (sub) { const s = document.createElement("span"); s.className = "sub"; s.textContent = sub; td.appendChild(s); }
      return td;
    };
    tr.append(cell(c.name, c.title), cell(c.company, c.website), cell(c.mobile || c.phone, c.mobile && c.phone ? c.phone : ""),
      cell(c.email), cell(c.scanned));
    const acts = document.createElement("td");
    acts.className = "acts";
    const b = (label, cls, fn) => { const x = document.createElement("button"); x.type = "button"; x.textContent = label; if (cls) x.className = cls; x.onclick = fn; acts.appendChild(x); };
    b("Edit", "", () => { editing = i; fillForm(c, false); say(""); $("form").scrollIntoView({ behavior: "smooth", block: "center" }); });
    b(".vcf", "", () => download(fileName(c) + ".vcf", vcf([c]), "text/vcard"));
    b("Delete", "del", () => {
      if (!confirm(`Delete ${c.name || "this contact"}?`)) return;
      contacts.splice(i, 1);
      if (editing === i) clearForm();
      storeContacts(); renderList();
    });
    tr.appendChild(acts);
    tb.appendChild(tr);
  });
  $("count").textContent = contacts.length;
  $("empty").hidden = contacts.length > 0 && tb.children.length > 0;
  $("empty").textContent = contacts.length ? "No contacts match your search." : "Saved contacts appear here. They are kept in this browser only.";
  $("allVcf").disabled = $("allCsv").disabled = $("clearAll").disabled = !contacts.length || !cardPy;
}

// ---------- wiring ----------
$("camera").addEventListener("change", (e) => { loadFile(e.target.files[0]); e.target.value = ""; });
$("upload").addEventListener("change", (e) => { loadFile(e.target.files[0]); e.target.value = ""; });
document.querySelectorAll(".sample").forEach((b) => b.addEventListener("click", () => loadFrom(b.dataset.src)));
$("rotate").addEventListener("click", rotate);
$("rescan").addEventListener("click", scan);
$("cleanOn").addEventListener("change", () => { if (source) scan(); });
$("showClean").addEventListener("change", showPreview);
$("save").addEventListener("click", saveContact);
$("saveVcf").addEventListener("click", () => { const c = readForm(); download(fileName(c) + ".vcf", vcf([c]), "text/vcard"); });
$("clearForm").addEventListener("click", clearForm);
$("search").addEventListener("input", renderList);
$("allVcf").addEventListener("click", () => download(`business-cards-${new Date().toISOString().slice(0, 10)}.vcf`, vcf(contacts), "text/vcard"));
$("allCsv").addEventListener("click", () => download(`business-cards-${new Date().toISOString().slice(0, 10)}.csv`,
  "﻿" + cardPy.csv_json(JSON.stringify(contacts)), "text/csv"));
$("clearAll").addEventListener("click", () => {
  if (!confirm(`Delete all ${contacts.length} saved contacts from this browser?`)) return;
  contacts = []; storeContacts(); renderList(); clearForm();
});

const drop = $("drop");
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); if (!busy && cardPy) drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("over")));
drop.addEventListener("drop", (e) => { e.preventDefault(); if (!busy && ocr) loadFile(e.dataTransfer.files[0]); });
window.addEventListener("paste", (e) => {
  const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
  if (item && ocr && !busy) loadFile(item.getAsFile());
});

renderList();
start();
