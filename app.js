const API = 'http://localhost:3000/api';

function getToken()        { return localStorage.getItem('fridge_token'); }
function setToken(t)       { localStorage.setItem('fridge_token', t); }
function getCurrentUser()  { try { return JSON.parse(localStorage.getItem('fridge_currentUser')); } catch { return null; } }
function setCurrentUser(u) { localStorage.setItem('fridge_currentUser', JSON.stringify(u)); }
function clearAuth()       { localStorage.removeItem('fridge_token'); localStorage.removeItem('fridge_currentUser'); }

function requireAuth() {
  const user = getCurrentUser();
  if (!user || !getToken()) { window.location.href = 'index.html'; return false; }
  return user;
}

function logout() {
  clearAuth();
  window.location.href = 'index.html';
}

async function apiFetch(path, options = {}) {
  const token   = getToken();
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = 'Bearer ' + token;
  const res  = await fetch(API + path, { ...options, headers });
  const data = await res.json();
  if (res.status === 401) { clearAuth(); window.location.href = 'index.html'; }
  return data;
}

async function apiLogin(email, password) {
  return await apiFetch('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
}

async function apiRegister(firstName, lastName, email, password) {
  return await apiFetch('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ first_name: firstName, last_name: lastName, email, password })
  });
}

async function getProducts(category = null) {
  const path = category ? `/products?category=${category}` : '/products';
  const res  = await apiFetch(path);
  return res.success ? res.data : [];
}

async function addProduct(product) {
  const res = await apiFetch('/products', {
    method: 'POST',
    body: JSON.stringify({
      name: product.name, category: product.category,
      qty: product.qty,   unit: product.unit,
      exp_date: product.expDate || product.exp_date
    })
  });
  return res.success ? res.data : null;
}

async function deleteProduct(id, reason = 'removed') {
  const res = await apiFetch(`/products/${id}`, { method: 'DELETE', body: JSON.stringify({ reason }) });
  return res.success;
}

async function getStats() {
  const res = await apiFetch('/stats/summary');
  return res.success ? res.data : { total: 0, expired: 0, expiring_soon: 0, fresh: 0 };
}

async function getWeeklyStats() {
  const res = await apiFetch('/stats/weekly');
  return res.success ? res.data : { labels: [], values: [] };
}

async function getMonthlyStats() {
  const res = await apiFetch('/stats/monthly');
  return res.success ? res.data : { labels: [], values: [] };
}

async function getRemovedProducts() {
  const res = await apiFetch('/products/removed/history');
  return res.success ? res.data : [];
}

async function getSensorData() {
  const res = await apiFetch('/sensor/summary');
  return res.success ? res.data : { temperature: null, humidity: null, connected: false };
}

async function getNotificationCount() {
  const stats = await getStats();
  return (stats.expired || 0) + (stats.expiring_soon || 0);
}

async function updateBadges() {
  const count = await getNotificationCount();
  document.querySelectorAll('.notif-badge').forEach(el => {
    el.textContent = count;
    el.style.display = count > 0 ? 'flex' : 'none';
  });
}

function getDaysUntilExpiry(expDate) {
  const today = new Date(); today.setHours(0,0,0,0);
  const exp   = new Date(expDate); exp.setHours(0,0,0,0);
  return Math.floor((exp - today) / 86400000);
}

function getExpiryStatus(expDate) {
  const days = getDaysUntilExpiry(expDate);
  if (days < 0)  return 'expired';
  if (days <= 3) return 'soon';
  return 'fresh';
}

function getExpiryDotClass(expDate) {
  const s = getExpiryStatus(expDate);
  return s === 'expired' ? 'expired' : s === 'soon' ? 'soon' : 'fresh';
}

function formatExpDate(expDate) {
  const d = new Date(expDate);
  return `${d.getDate()} ${d.toLocaleString('en',{month:'short'})} ${String(d.getFullYear()).slice(-2)}`;
}

const CATEGORIES = {
  vegetables: { label: 'Vegetables & Fruits', emoji: '🥦', color: '#10b981' },
  meat:       { label: 'Meat',                emoji: '🍗', color: '#ef4444' },
  dairy:      { label: 'Dairy',               emoji: '🥛', color: '#3b82f6' },
  frozen:     { label: 'Frozen',              emoji: '🍟', color: '#8b5cf6' },
  canned:     { label: 'Canned',              emoji: '🥫', color: '#f59e0b' },
  others:     { label: 'Others',              emoji: '🍫', color: '#6b7280' }
};

function getCategoryConfig(cat) {
  return CATEGORIES[cat] || { label: cat, emoji: '📦', color: '#6b7280' };
}

function showToast(message, type = 'success') {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.className = `toast ${type}`;
  requestAnimationFrame(() => toast.classList.add('show'));
  setTimeout(() => toast.classList.remove('show'), 3000);
}

function openModal(id)  { const m = document.getElementById(id); if (m) { m.classList.add('show');    document.body.style.overflow = 'hidden'; } }
function closeModal(id) { const m = document.getElementById(id); if (m) { m.classList.remove('show'); document.body.style.overflow = '';       } }

function toggleSidebar() {
  document.getElementById('sidebar')?.classList.toggle('open');
  document.getElementById('sidebarOverlay')?.classList.toggle('show');
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('menuBtn')?.addEventListener('click', toggleSidebar);
  document.getElementById('sidebarOverlay')?.addEventListener('click', toggleSidebar);

  document.querySelectorAll('.modal-overlay').forEach(modal => {
    modal.addEventListener('click', e => {
      if (e.target === modal) { modal.classList.remove('show'); document.body.style.overflow = ''; }
    });
  });

  const user = getCurrentUser();
  if (user) {
    document.querySelectorAll('.user-name-display').forEach(el => {
      el.textContent = (user.first_name || '') + ' ' + (user.last_name || '');
    });
    document.querySelectorAll('.user-avatar').forEach(el => {
      el.textContent = (user.first_name || 'U')[0].toUpperCase();
    });
  }

  if (getToken()) updateBadges();
});
