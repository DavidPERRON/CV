const STORAGE_KEY = "cv-agent-web-v1";

const methodologyText = `PROMPT MAÎTRE — MÉTHODOLOGIE D’ADAPTATION DE CV PAR POSTE

Version web retenue :
- zéro invention
- lecture intégrale de l’offre
- adaptation conservatrice et traçable
- pas de lettre de motivation
- positioning memo bref, factuel, jamais arrogant
- ordre de sortie :
  1. Lecture du poste
  2. Actifs de candidature mobilisables
  3. Gap analysis
  4. CV adapté complet`;

const defaultState = {
  mailboxes: {
    monitoring: {
      title: "Boîte 1 — veille",
      email: "",
      purpose: "alertes LinkedIn, veille, collecte",
      authMode: "app password / IMAP",
      notes: "séparée de la boîte de candidature",
    },
    applications: {
      title: "Boîte 2 — candidatures",
      email: "",
      purpose: "inscriptions ATS, confirmations, OTP email",
      authMode: "app password / future secure vault",
      notes: "dédiée aux comptes créés pour candidater",
    },
  },
  settings: {
    flexibilityMode: "balanced",
    minScore: 60,
    allowRemote: true,
    allowHybrid: true,
    allowOnsite: false,
    sectors: ["banking", "fintech", "applied AI"],
    targetCompanies: [],
    blacklistCompanies: [],
    positiveKeywords: ["executive", "director", "global", "strategy"],
    negativeKeywords: ["intern", "junior", "entry level", "stage"],
    geographies: ["France", "United Kingdom", "Europe"],
  },
  profile: {
    fullName: "",
    targetTitle: "",
    summary: "",
    masterCvText: "",
    coreFacts: [],
  },
  offers: [],
};

let state = loadState();
let currentOfferId = null;

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return structuredClone(defaultState);
    return deepMerge(structuredClone(defaultState), JSON.parse(raw));
  } catch {
    return structuredClone(defaultState);
  }
}

function saveState() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function deepMerge(target, source) {
  for (const key of Object.keys(source || {})) {
    if (Array.isArray(source[key])) target[key] = source[key];
    else if (source[key] && typeof source[key] === "object") target[key] = deepMerge(target[key] || {}, source[key]);
    else target[key] = source[key];
  }
  return target;
}

function listFromTextarea(value) {
  return value.split(/\n|,/).map(v => v.trim()).filter(Boolean);
}

function scoreOffer(offer) {
  const text = [offer.title, offer.company, offer.location, offer.sector, offer.description].join(" ").toLowerCase();
  const s = state.settings;
  const positiveHits = s.positiveKeywords.filter(k => k && text.includes(k.toLowerCase()));
  const negativeHits = s.negativeKeywords.filter(k => k && text.includes(k.toLowerCase()));

  let score = 50 + positiveHits.length * 8 - negativeHits.length * 10;
  if ((offer.company || "") && s.targetCompanies.some(c => c.toLowerCase() === (offer.company || "").toLowerCase())) score += 18;
  if ((offer.company || "") && s.blacklistCompanies.some(c => c.toLowerCase() === (offer.company || "").toLowerCase())) score -= 40;
  if ((offer.sector || "") && s.sectors.some(c => (offer.sector || "").toLowerCase().includes(c.toLowerCase()))) score += 12;
  if ((offer.location || "") && s.geographies.some(c => (offer.location || "").toLowerCase().includes(c.toLowerCase()))) score += 8;
  if (offer.workMode === "remote" && !s.allowRemote) score -= 20;
  if (offer.workMode === "hybrid" && !s.allowHybrid) score -= 20;
  if (offer.workMode === "onsite" && !s.allowOnsite) score -= 20;
  if (s.flexibilityMode === "strict") score += 10;
  if (s.flexibilityMode === "opportunistic") score -= 10;
  score = Math.max(0, Math.min(100, score));

  const fitSummary = [
    positiveHits.length ? "alignement lexical positif" : null,
    s.targetCompanies.includes(offer.company) ? "entreprise cible" : null,
    s.sectors.some(c => (offer.sector || "").toLowerCase().includes(c.toLowerCase())) ? "secteur cohérent" : null,
  ].filter(Boolean).join(", ") || "screening de base";

  const riskSummary = [
    negativeHits.length ? "mots-clés négatifs détectés" : null,
    s.blacklistCompanies.includes(offer.company) ? "entreprise blacklistée" : null,
    offer.workMode === "onsite" && !s.allowOnsite ? "onsite hors préférence" : null,
  ].filter(Boolean).join(", ") || "pas de risque majeur au niveau règles";

  return { score, positiveHits, negativeHits, fitSummary, riskSummary };
}

function addOffer(offer) {
  const scored = scoreOffer(offer);
  const id = crypto.randomUUID();
  state.offers.unshift({
    id,
    ...offer,
    score: scored.score,
    positiveHits: scored.positiveHits,
    negativeHits: scored.negativeHits,
    fitSummary: scored.fitSummary,
    riskSummary: scored.riskSummary,
    status: scored.score >= state.settings.minScore ? "retained" : "screened_out",
    draft: null,
    createdAt: new Date().toISOString(),
  });
  currentOfferId = id;
  saveState();
  renderAll();
}

function generateDraftForOffer(offer) {
  const profile = state.profile;
  const positioningMemo = `Le poste semble combiner exposition senior, crédibilité métier et exécution disciplinée. Pour ${offer.company || "l’employeur"}, le dossier doit présenter une proximité réelle avec ${offer.title}, sans sur-qualification rhétorique ni emphase inutile.`;
  const mobilizableAssets = [
    "Seniority crédible et exposition exécutive sur des sujets complexes",
    "Capacité à articuler business, transformation et relations de haut niveau",
    "Positionnement trans-sectoriel uniquement là où le CV maître l’autorise",
    "Narration sobre, défendable et orientée rôle"
  ].join("\n");
  const gapAnalysis = "Les correspondances fortes doivent être explicites. Les proximités partielles doivent rester qualifiées comme telles. Tout écart réel doit être formulé proprement, sans brouillard rédactionnel.";
  const adaptedCvText = [
    `Executive Summary\n${profile.summary || "[Résumé exécutif à compléter à partir du CV maître]"}`,
    `Target Role\n${offer.title}`,
    "Core Relevance\n- Reprendre uniquement des éléments attestés du CV maître\n- Mettre en avant les expériences les plus proches du besoin\n- Conserver une densité utile, jamais décorative",
    "Professional Experience\n[Adapter ici les expériences réelles du CV maître]",
    "Education\n[Reprendre la formation réelle]",
    "Additional Information\n[Langues, géographies, éléments additionnels vérifiables]"
  ].join("\n\n");

  offer.draft = {
    positioningMemo,
    mobilizableAssets,
    gapAnalysis,
    adaptedCvText,
    version: (offer.draft?.version || 0) + 1,
    validated: false,
    updatedAt: new Date().toISOString(),
  };
  offer.status = "cv_ready";
  saveState();
  renderAll();
}

async function downloadDraftAsDocx(offer) {
  if (!offer?.draft) return;
  const { Document, Packer, Paragraph, HeadingLevel, TextRun } = window.docx;
  const linesToParagraphs = (text) => String(text || "").split("\n\n").map(block => new Paragraph(block));

  const doc = new Document({
    sections: [{
      properties: {},
      children: [
        new Paragraph({ text: state.profile.fullName || "Candidate", heading: HeadingLevel.TITLE }),
        new Paragraph({ children: [new TextRun({ text: state.profile.targetTitle || offer.title, italics: true })] }),
        new Paragraph({ text: "1. Lecture du poste", heading: HeadingLevel.HEADING_1 }),
        ...linesToParagraphs(offer.draft.positioningMemo),
        new Paragraph({ text: "2. Actifs de candidature mobilisables", heading: HeadingLevel.HEADING_1 }),
        ...linesToParagraphs(offer.draft.mobilizableAssets),
        new Paragraph({ text: "3. Gap analysis", heading: HeadingLevel.HEADING_1 }),
        ...linesToParagraphs(offer.draft.gapAnalysis),
        new Paragraph({ text: "4. CV adapté", heading: HeadingLevel.HEADING_1 }),
        ...linesToParagraphs(offer.draft.adaptedCvText),
      ],
    }],
  });

  const blob = await Packer.toBlob(doc);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${slugify(offer.company || "company")}_${slugify(offer.title)}_draft_v${offer.draft.version}.docx`;
  a.click();
  URL.revokeObjectURL(url);
}

function slugify(value) {
  return String(value || "draft").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

function validateOfferDraft(offer) {
  if (!offer?.draft) return;
  offer.draft.validated = true;
  offer.status = "validated";
  saveState();
  renderAll();
}

function prepareSend(offer) {
  offer.status = "ready_to_send";
  saveState();
  renderAll();
}

function markSubmitted(offer) {
  offer.status = "submitted";
  saveState();
  renderAll();
}

function renderStats() {
  const offers = state.offers;
  const cards = [
    ["Offres totales", offers.length],
    ["Retenues", offers.filter(o => o.status === "retained").length],
    ["CV prêts", offers.filter(o => o.status === "cv_ready").length],
    ["Validées / prêtes", offers.filter(o => ["validated","ready_to_send"].includes(o.status)).length],
  ];
  document.getElementById("statsCards").innerHTML = cards.map(([label, value]) => `\n    <div class="card stat-card"><div class="label">${label}</div><div class="value">${value}</div></div>\n  `).join("");
}

function tierClass(score) {
  if (score >= 80) return "top";
  if (score >= 60) return "good";
  if (score >= 40) return "mid";
  return "low";
}

function renderPriorityOffers() {
  const container = document.getElementById("priorityOffers");
  const offers = [...state.offers].sort((a,b) => b.score - a.score).slice(0, 6);
  if (!offers.length) {
    container.innerHTML = `<div class="small">Aucune offre pour l’instant.</div>`;
    return;
  }
  container.innerHTML = offers.map(offer => `\n    <div class="priority-item">\n      <div class="detail-header">\n        <div>\n          <strong>${escapeHtml(offer.title)}</strong>\n          <div class="small">${escapeHtml(offer.company || "—")} · ${escapeHtml(offer.location || "—")}</div>\n        </div>\n        <span class="badge ${tierClass(offer.score)}">${offer.score}</span>\n      </div>\n      <div class="small">${escapeHtml(offer.fitSummary)}</div>\n    </div>\n  `).join("");
}

function renderMailboxes() {
  const grid = document.getElementById("mailboxesGrid");
  grid.innerHTML = Object.entries(state.mailboxes).map(([key, box]) => `\n    <div class="mailbox-card">\n      <div class="mailbox-title">${escapeHtml(box.title)}</div>\n      <div class="meta">Usage : ${escapeHtml(box.purpose)}</div>\n      <label>Email<input data-mailbox="${key}" data-field="email" value="${escapeAttr(box.email)}" /></label>\n      <label>Mode d’authentification<input data-mailbox="${key}" data-field="authMode" value="${escapeAttr(box.authMode)}" /></label>\n      <label>Notes<textarea data-mailbox="${key}" data-field="notes">${escapeHtml(box.notes)}</textarea></label>\n    </div>\n  `).join("");

  grid.querySelectorAll("input, textarea").forEach(el => {
    el.addEventListener("change", (e) => {
      const key = e.target.dataset.mailbox;
      const field = e.target.dataset.field;
      state.mailboxes[key][field] = e.target.value;
      saveState();
    });
  });
}

function renderSettings() {
  const form = document.getElementById("filtersForm");
  const s = state.settings;
  form.flexibilityMode.value = s.flexibilityMode;
  form.minScore.value = s.minScore;
  form.allowRemote.checked = s.allowRemote;
  form.allowHybrid.checked = s.allowHybrid;
  form.allowOnsite.checked = s.allowOnsite;
  form.sectors.value = s.sectors.join(", ");
  form.targetCompanies.value = s.targetCompanies.join(", ");
  form.blacklistCompanies.value = s.blacklistCompanies.join(", ");
  form.positiveKeywords.value = s.positiveKeywords.join(", ");
  form.negativeKeywords.value = s.negativeKeywords.join(", ");
  form.geographies.value = s.geographies.join(", ");

  const p = state.profile;
  const pForm = document.getElementById("profileForm");
  pForm.fullName.value = p.fullName;
  pForm.targetTitle.value = p.targetTitle;
  pForm.summary.value = p.summary;
  pForm.masterCvText.value = p.masterCvText;
  pForm.coreFacts.value = p.coreFacts.join("\n");

  document.getElementById("methodologyPreview").textContent = methodologyText;
}

function renderOffers() {
  const filter = document.getElementById("statusFilter").value;
  const rows = state.offers.filter(offer => filter === "all" || offer.status === filter);
  const wrap = document.getElementById("offersTableWrap");
  if (!rows.length) {
    wrap.innerHTML = `<div class="small">Aucune offre à afficher.</div>`;
    return;
  }
  wrap.innerHTML = `\n    <table class="table">\n      <thead>\n        <tr><th>Score</th><th>Offre</th><th>Mode</th><th>Statut</th><th>Fit</th></tr>\n      </thead>\n      <tbody>\n        ${rows.map(offer => `\n          <tr>\n            <td><span class="badge ${tierClass(offer.score)}">${offer.score}</span></td>\n            <td>\n              <button class="offer-link-btn" data-offer-id="${offer.id}">\n                <strong>${escapeHtml(offer.title)}</strong>\n                <span>${escapeHtml(offer.company || "—")}</span>\n              </button>\n            </td>\n            <td>${escapeHtml(offer.workMode || "—")}</td>\n            <td>${escapeHtml(offer.status)}</td>\n            <td>${escapeHtml(offer.fitSummary)}</td>\n          </tr>\n        `).join("")}\n      </tbody>\n    </table>\n  `;

  wrap.querySelectorAll("[data-offer-id]").forEach(btn => {
    btn.addEventListener("click", () => {
      currentOfferId = btn.dataset.offerId;
      document.querySelector('[data-view="workflow"]').click();
      renderOfferDetail();
    });
  });
}

function renderOfferDetail() {
  const pane = document.getElementById("offerDetailPane");
  const offer = state.offers.find(o => o.id === currentOfferId);
  if (!offer) {
    pane.innerHTML = `<div class="detail-empty">Sélectionnez une offre depuis la table pour afficher le détail et générer le Word.</div>`;
    return;
  }
  pane.innerHTML = `\n    <div class="detail-box">\n      <div class="detail-header">\n        <div>\n          <h3>${escapeHtml(offer.title)}</h3>\n          <div class="small">${escapeHtml(offer.company || "—")} · ${escapeHtml(offer.location || "—")} · ${escapeHtml(offer.workMode || "—")}</div>\n        </div>\n        <div class="detail-actions">\n          <span class="badge ${tierClass(offer.score)}">${offer.score}</span>\n          <button id="genDraftBtn" class="secondary">Générer Word</button>\n          <button id="validateDraftBtn" class="secondary" ${offer.draft ? "" : "disabled"}>Valider</button>\n          <button id="prepareSendBtn" class="secondary" ${offer.draft?.validated ? "" : "disabled"}>Préparer envoi</button>\n          <button id="markSubmittedBtn" class="secondary" ${offer.status === "ready_to_send" ? "" : "disabled"}>Marquer envoyé</button>\n        </div>\n      </div>\n      <div class="kv">\n        <div>Statut</div><div>${escapeHtml(offer.status)}</div>\n        <div>Fit summary</div><div>${escapeHtml(offer.fitSummary)}</div>\n        <div>Risk summary</div><div>${escapeHtml(offer.riskSummary)}</div>\n        <div>Mots-clés positifs</div><div>${escapeHtml((offer.positiveHits || []).join(", ") || "—")}</div>\n        <div>Mots-clés négatifs</div><div>${escapeHtml((offer.negativeHits || []).join(", ") || "—")}</div>\n        <div>URL</div><div>${offer.sourceUrl ? `<a href="${escapeAttr(offer.sourceUrl)}" target="_blank" rel="noopener">ouvrir la source</a>` : "—"}</div>\n      </div>\n      <div class="pre">${escapeHtml(offer.description)}</div>\n      ${offer.draft ? `\n        <hr />\n        <div class="detail-header">\n          <h3>Draft v${offer.draft.version}</h3>\n          <div class="detail-actions">\n            <button id="downloadDraftBtn">Télécharger le Word</button>\n          </div>\n        </div>\n        <div class="small">validated: ${offer.draft.validated ? "yes" : "no"}</div>\n        <div class="cards two">\n          <div class="pre">${escapeHtml(offer.draft.positioningMemo)}</div>\n          <div class="pre">${escapeHtml(offer.draft.gapAnalysis)}</div>\n        </div>\n      ` : ``}\n    </div>\n  `;

  document.getElementById("genDraftBtn").addEventListener("click", () => generateDraftForOffer(offer));
  const validateBtn = document.getElementById("validateDraftBtn");
  if (validateBtn) validateBtn.addEventListener("click", () => validateOfferDraft(offer));
  const prepBtn = document.getElementById("prepareSendBtn");
  if (prepBtn) prepBtn.addEventListener("click", () => prepareSend(offer));
  const sentBtn = document.getElementById("markSubmittedBtn");
  if (sentBtn) sentBtn.addEventListener("click", () => markSubmitted(offer));
  const dlBtn = document.getElementById("downloadDraftBtn");
  if (dlBtn) dlBtn.addEventListener("click", () => downloadDraftAsDocx(offer));
}

function renderAll() {
  renderStats();
  renderPriorityOffers();
  renderMailboxes();
  renderSettings();
  renderOffers();
  renderOfferDetail();
}

function attachEvents() {
  document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.dataset.view).classList.add("active");
      document.getElementById("view-title").textContent = btn.textContent;
      if (btn.dataset.view === "workflow") renderOfferDetail();
    });
  });

  document.getElementById("filtersForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    state.settings = {
      flexibilityMode: f.get("flexibilityMode"),
      minScore: Number(f.get("minScore")) || 60,
      allowRemote: !!f.get("allowRemote"),
      allowHybrid: !!f.get("allowHybrid"),
      allowOnsite: !!f.get("allowOnsite"),
      sectors: listFromTextarea(f.get("sectors") || ""),
      targetCompanies: listFromTextarea(f.get("targetCompanies") || ""),
      blacklistCompanies: listFromTextarea(f.get("blacklistCompanies") || ""),
      positiveKeywords: listFromTextarea(f.get("positiveKeywords") || ""),
      negativeKeywords: listFromTextarea(f.get("negativeKeywords") || ""),
      geographies: listFromTextarea(f.get("geographies") || ""),
    };
    saveState();
    rerunScores();
    renderAll();
  });

  document.getElementById("profileForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    state.profile = {
      fullName: f.get("fullName") || "",
      targetTitle: f.get("targetTitle") || "",
      summary: f.get("summary") || "",
      masterCvText: f.get("masterCvText") || "",
      coreFacts: listFromTextarea(f.get("coreFacts") || ""),
    };
    saveState();
    renderAll();
  });

  document.getElementById("offerForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    addOffer({
      title: f.get("title"),
      company: f.get("company"),
      location: f.get("location"),
      workMode: f.get("workMode"),
      sector: f.get("sector"),
      sourceUrl: f.get("sourceUrl"),
      description: f.get("description"),
    });
    e.target.reset();
  });

  document.getElementById("statusFilter").addEventListener("change", renderOffers);

  document.getElementById("exportStateBtn").addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(state, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "cv-agent-web-state.json";
    a.click();
    URL.revokeObjectURL(url);
  });

  document.getElementById("importStateInput").addEventListener("change", async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    state = deepMerge(structuredClone(defaultState), JSON.parse(text));
    saveState();
    renderAll();
  });

  document.getElementById("resetDemoBtn").addEventListener("click", () => {
    if (!confirm("Réinitialiser toutes les données locales du navigateur ?")) return;
    state = structuredClone(defaultState);
    saveState();
    currentOfferId = null;
    renderAll();
  });
}

function rerunScores() {
  state.offers.forEach(offer => {
    const scored = scoreOffer(offer);
    offer.score = scored.score;
    offer.positiveHits = scored.positiveHits;
    offer.negativeHits = scored.negativeHits;
    offer.fitSummary = scored.fitSummary;
    offer.riskSummary = scored.riskSummary;
    if (!["cv_ready","validated","ready_to_send","submitted"].includes(offer.status)) {
      offer.status = scored.score >= state.settings.minScore ? "retained" : "screened_out";
    }
  });
  saveState();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}[c]));
}
function escapeAttr(value) { return escapeHtml(value); }

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("./sw.js").catch(() => {}));
}

attachEvents();
renderAll();
