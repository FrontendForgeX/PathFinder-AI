'use strict';

const state = { results: [], saved: [], page: 'discover', layout: 'grid' };
const element = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[character]);
}

function truncate(value, limit = 175) {
  const text = String(value || 'No description available.');
  return text.length > limit ? `${text.slice(0, limit).trim()}…` : text;
}

let toastTimer;
function toast(message) {
  const node = element('toast');
  node.textContent = message;
  node.classList.add('visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove('visible'), 3000);
}

function notify(message, visible = true) {
  element('notice').classList.toggle('hidden', !visible);
  element('notice').lastElementChild.textContent = message;
}

async function loadSaved() {
  try {
    const response = await fetch('/api/saved');
    if (!response.ok) throw new Error('Could not load reading list');
    const data = await response.json();
    state.saved = Array.isArray(data) ? data : [];
  } catch {
    state.saved = [];
  }
  element('savedCount').textContent = state.saved.length;
}

function filteredResults() {
  const query = element('keyword').value.trim().toLowerCase();
  const status = element('status').value;
  const sort = element('sort').value;
  const entries = state.page === 'saved' ? state.saved : state.results;
  const matching = entries.filter((entry) => {
    const text = [entry.name, entry.description, entry.source].join(' ').toLowerCase();
    return (status === 'ALL' || entry.status === status) && text.includes(query);
  });
  if (sort === 'name') matching.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  if (sort === 'status') {
    const rank = { ONGOING: 0, UPCOMING: 1, UNKNOWN: 2, ENDED: 3 };
    matching.sort((a, b) => (rank[a.status] ?? 4) - (rank[b.status] ?? 4));
  }
  if (sort === 'score') matching.sort((a, b) => (b.score || 0) - (a.score || 0));
  return matching;
}

function opportunityCard(item, index) {
  const saved = state.saved.some((entry) => entry.url === item.url);
  const status = String(item.status || 'UNKNOWN');
  const name = escapeHtml(item.name);
  const url = escapeHtml(item.url);
  const reasons = Array.isArray(item.reasons) ? item.reasons : [];

  return `<article class="result-card" style="animation-delay:${Math.min(index, 9) * 35}ms">
    <div class="card-head"><span class="card-host">${escapeHtml(item.source || 'Unverified source')}</span><span class="match-score">${escapeHtml(item.score ?? '—')} MATCH SCORE</span></div>
    <h3>${name}</h3>
    <p class="description">${escapeHtml(truncate(item.description))}</p>
    <div class="tags"><span class="tag ${escapeHtml(status.toLowerCase())}">${escapeHtml(status)}</span><span class="tag">${escapeHtml(item.kind || 'UNVERIFIED')}</span>${item.mode && item.mode !== 'UNKNOWN' ? `<span class="tag">${escapeHtml(item.mode)}</span>` : ''}</div>
    <div class="info-rows">
      <div class="info-row"><span>Event date</span><strong>${escapeHtml(item.event_date || 'Not confirmed')}</strong></div>
      <div class="info-row"><span>Deadline</span><strong>${escapeHtml(item.deadline || 'Not confirmed')}</strong></div>
      <div class="info-row"><span>Registration</span><strong>${escapeHtml(item.registration || 'Unverified')}</strong></div>
      <div class="info-row"><span>Research</span><strong>${escapeHtml(item.research_source || 'Saved reference')}</strong></div>
    </div>
    ${reasons.length ? `<div class="match-reasons">WHY IT MATCHES — ${escapeHtml(reasons.join(' · '))}</div>` : ''}
    <div class="card-actions"><a class="visit-link" href="${url}" target="_blank" rel="noopener noreferrer">View opportunity <span>↗</span></a><button class="save-btn" data-save="${url}" title="${saved ? 'Remove from reading list' : 'Add to reading list'}" aria-label="${saved ? 'Remove from reading list' : 'Save opportunity'}">${saved ? '♥' : '♡'}</button><button class="copy-btn" data-copy="${url}" title="Copy opportunity link" aria-label="Copy opportunity link">↗</button></div>
  </article>`;
}

function render() {
  const matching = filteredResults();
  const results = element('results');
  results.classList.toggle('list-view', state.layout === 'list');
  results.innerHTML = matching.length
    ? matching.map(opportunityCard).join('')
    : '<div class="empty"><strong>Nothing on the radar yet.</strong>Try another filter or run a new search.</div>';

  results.querySelectorAll('[data-save]').forEach((button) => {
    button.addEventListener('click', () => toggleSaved(button.dataset.save));
  });
  results.querySelectorAll('[data-copy]').forEach((button) => {
    button.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(button.dataset.copy); toast('Link copied to clipboard'); }
      catch { toast('Could not copy link'); }
    });
  });
}

async function toggleSaved(url) {
  const item = [...state.results, ...state.saved].find((entry) => entry.url === url);
  if (!item) return;
  const remove = state.saved.some((entry) => entry.url === url);
  try {
    const response = await fetch('/api/saved', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item, remove })
    });
    if (!response.ok) throw new Error('Could not update reading list');
    await loadSaved();
    toast(remove ? 'Removed from reading list' : 'Saved to reading list');
    render();
  } catch (error) {
    toast(error.message);
  }
}

function openPage(page) {
  state.page = page;
  element('discover').classList.toggle('active', page === 'discover');
  element('saved').classList.toggle('active', page === 'saved');
  element('sectionTitle').innerHTML = page === 'saved' ? 'Your reading list<span class="orange-period">.</span>' : 'Your discoveries<span class="orange-period">.</span>';
  element('resultsCaption').textContent = page === 'saved'
    ? 'Opportunities you saved to revisit later.'
    : 'A considered shortlist of opportunities for your next move.';
  notify('', false);
  render();
}

async function search(refresh = false) {
  openPage('discover');
  const profile = Object.fromEntries(new FormData(element('profile')).entries());
  profile.refresh = refresh;
  element('run').disabled = true;
  element('refresh').disabled = true;
  element('run').querySelector('span:nth-child(2)').textContent = 'Researching…';
  notify('Searching opportunities and checking source pages. This may take a moment.');
  element('results').innerHTML = '';

  try {
    const response = await fetch('/api/search', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Search failed');
    state.results = data.items || [];
    element('count').textContent = state.results.length;
    element('current').textContent = state.results.filter((item) => ['UPCOMING', 'ONGOING'].includes(item.status)).length;
    element('source').textContent = String(data.source || 'UNKNOWN').replaceAll('_', ' ').toUpperCase();
    await loadSaved();
    const errors = (data.errors || []).join(' • ');
    notify(errors || (state.results.length ? 'Results are estimates. Verify eligibility, dates and registration with organizers.' : 'No results found. Adjust your profile or try a fresh search.'));
    render();
    if (state.results.length) toast(`Found ${state.results.length} opportunities`);
  } catch (error) {
    state.results = [];
    notify(error.message);
  } finally {
    element('run').disabled = false;
    element('refresh').disabled = false;
    element('run').querySelector('span:nth-child(2)').textContent = 'Explore opportunities';
  }
}

function initialize() {
  element('today').textContent = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date());
  element('profile').addEventListener('submit', (event) => { event.preventDefault(); search(); });
  element('refresh').addEventListener('click', () => search(true));
  element('keyword').addEventListener('input', render);
  element('status').addEventListener('change', render);
  element('sort').addEventListener('change', render);
  element('discover').addEventListener('click', () => openPage('discover'));
  element('saved').addEventListener('click', async () => { await loadSaved(); openPage('saved'); });
  element('gridView').addEventListener('click', () => switchLayout('grid'));
  element('listView').addEventListener('click', () => switchLayout('list'));
  loadSaved();
}

function switchLayout(layout) {
  state.layout = layout;
  element('gridView').classList.toggle('selected', layout === 'grid');
  element('listView').classList.toggle('selected', layout === 'list');
  render();
}

initialize();
