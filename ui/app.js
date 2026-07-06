const statusFilter = document.getElementById("statusFilter");
const countryFilter = document.getElementById("countryFilter");
const searchCountry = document.getElementById("searchCountry");
const dateField = document.getElementById("dateField");
const dateFrom = document.getElementById("dateFrom");
const dateTo = document.getElementById("dateTo");
const searchQuery = document.getElementById("searchQuery");
const clearFilters = document.getElementById("clearFilters");
const refreshBtn = document.getElementById("refreshBtn");
const jobList = document.getElementById("jobList");
const emptyState = document.getElementById("emptyState");
const statusBar = document.getElementById("statusBar");
const template = document.getElementById("jobCardTemplate");

let debounceTimer;

function showStatus(message, isError = false) {
  statusBar.hidden = false;
  statusBar.textContent = message;
  statusBar.style.background = isError
    ? "rgba(255, 107, 107, 0.12)"
    : "rgba(91, 140, 255, 0.12)";
  statusBar.style.borderColor = isError
    ? "rgba(255, 107, 107, 0.25)"
    : "rgba(91, 140, 255, 0.25)";
  statusBar.style.color = isError ? "#ffc9c9" : "#c9d8ff";
}

function statusLabel(status) {
  if (status === "To Apply") return "To Apply";
  if (status === "Applied") return "Applied";
  if (status === "Rejected") return "Rejected";
  return status;
}

function fillCountrySelect(select, countries) {
  const current = select.value;
  select.innerHTML = "";
  for (const item of countries) {
    const opt = document.createElement("option");
    opt.value = item.code;
    opt.textContent = item.label;
    select.appendChild(opt);
  }
  if ([...select.options].some((o) => o.value === current)) {
    select.value = current;
  }
}

async function loadCountries() {
  try {
    const res = await fetch("/api/countries");
    const data = await res.json();
    const countries = data.countries || [{ code: "all", label: "All countries" }];
    fillCountrySelect(countryFilter, countries);
    fillCountrySelect(searchCountry, countries);
  } catch {
    // keep default option
  }
}

function buildQuery() {
  const params = new URLSearchParams();
  params.set("status", statusFilter.value);
  params.set("date_field", dateField.value);
  if (countryFilter.value && countryFilter.value !== "all") {
    params.set("country", countryFilter.value);
  }
  if (dateFrom.value) params.set("date_from", dateFrom.value);
  if (dateTo.value) params.set("date_to", dateTo.value);
  if (searchQuery.value.trim()) params.set("q", searchQuery.value.trim());
  return params.toString();
}

async function searchAndReload() {
  refreshBtn.disabled = true;
  const scope =
    searchCountry.value === "all"
      ? "all countries"
      : searchCountry.value;
  showStatus(`Running job-finder skill (${scope})...`);

  try {
    const res = await fetch("/api/jobs/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ country: searchCountry.value }),
    });
    const data = await res.json();
    if (!data.ok) {
      showStatus(data.message || "Search failed", true);
      return;
    }

    const r = data.result;
    const names = (r.new_jobs || [])
      .slice(0, 3)
      .map((j) => j.company)
      .join(", ");
    const linkedinPart = r.linkedin_scanned
      ? `, ${r.linkedin_scanned} from LinkedIn`
      : "";
    const skill = r.skill ? `${r.skill}: ` : "";
    const summary = r.added
      ? `${skill}Added ${r.added} new job${r.added === 1 ? "" : "s"}${names ? `: ${names}` : ""} (${r.scanned} scanned${linkedinPart})`
      : `${skill}No new jobs (${r.scanned} scanned${linkedinPart})`;
    showStatus(summary);
    await loadJobs();
  } catch (err) {
    showStatus("Search error: " + err.message, true);
  } finally {
    refreshBtn.disabled = false;
  }
}

async function loadJobs() {
  try {
    const res = await fetch(`/api/jobs?${buildQuery()}`);
    const data = await res.json();
    renderJobs(data.jobs || []);
  } catch (err) {
    showStatus("Failed to load jobs: " + err.message, true);
  }
}

function renderJobs(jobs) {
  jobList.innerHTML = "";
  const sorted = [...jobs].sort(
    (a, b) =>
      (b.match_score ?? 0) - (a.match_score ?? 0) ||
      (b.date_found || "").localeCompare(a.date_found || "")
  );
  emptyState.hidden = sorted.length > 0;

  for (const job of sorted) {
    const node = template.content.cloneNode(true);

    node.querySelector(".company").textContent = job.company || "—";
    node.querySelector(".title").textContent = job.title || "—";

    const badge = node.querySelector(".status-badge");
    badge.textContent = statusLabel(job.status);
    badge.dataset.status = job.status || "";

    const meta = node.querySelector(".meta");
    const parts = [];
    if (job.match_score != null) parts.push(`Resume match: ${job.match_score}%`);
    const bd = job.match_breakdown;
    if (bd && (bd.primary?.length || bd.secondary?.length)) {
      const skills = [...(bd.primary || []), ...(bd.secondary || [])].slice(0, 3);
      if (skills.length) parts.push(`Skills: ${skills.join(", ")}`);
    }
    if (job.country) parts.push(`Country: ${job.country}`);
    else if (job.location) parts.push(`Location: ${job.location}`);
    if (job.date_found) parts.push(`Found: ${job.date_found}`);
    if (job.date_applied) parts.push(`Applied: ${job.date_applied}`);
    if (job.relocate) parts.push(`Relocate: ${job.relocate}`);
    if (job.has_autofill) parts.push("autofill ready");
    meta.textContent = parts.join(" · ");

    const notes = node.querySelector(".notes");
    notes.textContent = job.notes || "";
    notes.hidden = !job.notes;

    const fillBtn = node.querySelector(".fill-btn");
    const appliedBtn = node.querySelector(".applied-btn");
    const linkBtn = node.querySelector(".link-btn");

    if (job.apply_url) {
      linkBtn.href = job.apply_url;
    } else {
      linkBtn.hidden = true;
    }

    if (job.status === "Applied") {
      fillBtn.disabled = true;
      appliedBtn.disabled = true;
      appliedBtn.textContent = "Applied ✓";
    }

    const card = node.querySelector(".job-card");
    if (card && job.url) {
      card.dataset.url = job.url;
    }

    fillBtn.addEventListener("click", () => fillJob(job, fillBtn));
    appliedBtn.addEventListener("click", () => markApplied(job, appliedBtn, card));

    jobList.appendChild(node);
  }
}

async function fillJob(job, btn) {
  btn.disabled = true;
  showStatus(`Opening ${job.company}...`);

  try {
    const res = await fetch("/api/jobs/fill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company: job.company, url: job.url || job.id }),
    });
    const data = await res.json();
    if (!data.ok) {
      showStatus(data.message || "Failed to fill form", true);
    } else {
      showStatus(data.message);
    }
  } catch (err) {
    showStatus("Error: " + err.message, true);
  } finally {
    btn.disabled = false;
  }
}

async function markApplied(job, btn, cardEl) {
  if (!confirm(`Mark "${job.company}" as applied?`)) return;

  btn.disabled = true;
  const removeFromList = statusFilter.value === "To Apply";

  try {
    const res = await fetch("/api/jobs/mark-applied", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        company: job.company,
        url: job.url || job.id,
      }),
    });
    const data = await res.json();
    if (!data.ok) {
      showStatus(data.error || "Failed to update status", true);
      btn.disabled = false;
      return;
    }

    showStatus(`${job.company} marked as applied ✓`);

    if (removeFromList && cardEl) {
      cardEl.remove();
      if (!jobList.querySelector(".job-card")) {
        emptyState.hidden = false;
      }
      return;
    }

    if (cardEl) {
      const badge = cardEl.querySelector(".status-badge");
      if (badge) {
        badge.textContent = "Applied";
        badge.dataset.status = "Applied";
      }
      const fillBtn = cardEl.querySelector(".fill-btn");
      if (fillBtn) fillBtn.disabled = true;
      btn.textContent = "Applied ✓";
    }
  } catch (err) {
    showStatus("Error: " + err.message, true);
    btn.disabled = false;
  }
}

function scheduleLoad() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(loadJobs, 250);
}

[statusFilter, countryFilter, dateField, dateFrom, dateTo].forEach((el) => {
  el.addEventListener("change", loadJobs);
});
searchQuery.addEventListener("input", scheduleLoad);

clearFilters.addEventListener("click", () => {
  statusFilter.value = "To Apply";
  countryFilter.value = "all";
  searchCountry.value = "all";
  dateField.value = "found";
  dateFrom.value = "";
  dateTo.value = "";
  searchQuery.value = "";
  loadJobs();
});

refreshBtn.addEventListener("click", searchAndReload);

loadCountries().then(loadJobs);
