#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const cdpUrl = process.env.BIS_MAC_CHROME_CDP_URL || 'http://127.0.0.1:9222';
const apiBaseUrl = (process.env.BIS_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const endpointUrl = `${apiBaseUrl}/admin/ingest-browser-items`;
const outputPath = path.join(__dirname, 'mac_browser_scan_output.json');
const scanMode = (process.env.BIS_BROWSER_SCAN_MODE || 'stdout').toLowerCase();

const CONVERSATION_INTENT_TERMS = [
  'can anyone recommend',
  'looking for',
  'who does',
  'any suggestions',
  'need a tattoo artist',
  'cover up recommendation',
  'black and grey recommendation',
  'memorial tattoo recommendation',
  'booked with',
  'experience with',
  'has anyone used',
  'availability',
  'iso',
  'in search of',
  'recommend'
];

const LOCAL_TERMS = [
  'edmonton',
  'yeg',
  'alberta',
  'st albert',
  'sherwood park',
  'spruce grove',
  'leduc'
];

const TOPIC_TERMS = {
  tattoo: [
    'tattoo',
    'tattoos',
    'tattoo artist',
    'flash tattoo',
    'fineline',
    'fine line',
    'watercolor',
    'black and grey',
    'black & grey',
    'cover up',
    'coverup',
    'memorial piece',
    'walk-in',
    'walk in'
  ],
  trades: ['plumber', 'electrician', 'contractor', 'renovation', 'handyman'],
  auto: ['mechanic', 'body shop', 'auto repair', 'oil change', 'car'],
  motorcycle: ['motorcycle', 'bike shop', 'ktm', 'yamaha', 'honda'],
  fitness: ['gym', 'trainer', 'fitness', 'workout'],
  beauty: ['lashes', 'nails', 'brows', 'salon'],
  medical: ['dentist', 'doctor', 'clinic', 'physio', 'massage'],
  parenting: ['daycare', 'kids', 'parenting', 'childcare'],
  real_estate: ['realtor', 'mortgage', 'home inspector', 'real estate'],
  job: ['hiring', 'job', 'position', 'employment']
};

const DEFAULT_GROUP_TARGETS = [
  { name: 'Edmonton Tattoo Community', url: 'https://www.facebook.com/groups/edmontontattoocommunity/' },
  { name: 'Edmonton Alberta Local Businesses & Recommendations', url: 'https://www.facebook.com/groups/edmontonalbertabusinesses/' },
  { name: 'Edmonton Alberta Small Businesses and Local Services', url: 'https://www.facebook.com/groups/smallbusinessedmonton/' },
  { name: 'The ORIGINAL St. Albert Chat', url: 'https://www.facebook.com/groups/stalbertchat/' },
  { name: 'Sherwood Park Community & Area Info', url: 'https://www.facebook.com/groups/824098623424214/' },
  { name: 'Spruce Grove / Stony Plain and Parkland County Local Chat Group', url: 'https://www.facebook.com/groups/394064004082927/' },
  { name: 'Leduc Local Chat', url: 'https://www.facebook.com/groups/505641606871354/' },
  { name: 'Edmonton Moms Community Group', url: 'https://www.facebook.com/groups/edmontonmomscommunity/' }
];

const groupTargets = parseGroupTargets();

function parseGroupTargets() {
  const raw = process.env.BIS_FACEBOOK_GROUP_URLS || process.env.BIS_BROWSER_SCAN_URLS || '';
  if (!raw.trim()) return DEFAULT_GROUP_TARGETS;
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed
        .map((item) => {
          if (typeof item === 'string') return { name: item, url: item };
          if (item && typeof item.url === 'string') return { name: item.name || item.url, url: item.url };
          return null;
        })
        .filter(Boolean);
    }
  } catch {}
  return raw
    .split(/\r?\n|,/) 
    .map((value) => value.trim())
    .filter(Boolean)
    .map((url) => ({ name: url, url }));
}

function findMatches(text, terms) {
  const lower = text.toLowerCase();
  return terms.filter((term) => lower.includes(term));
}

function classifyBlock(text) {
  const conversationIntentTerms = findMatches(text, CONVERSATION_INTENT_TERMS);
  const localTerms = findMatches(text, LOCAL_TERMS);

  let topicTag = 'other';
  let tattooTerms = [];
  for (const [tag, terms] of Object.entries(TOPIC_TERMS)) {
    const matches = findMatches(text, terms);
    if (matches.length > 0) {
      topicTag = tag;
      if (tag === 'tattoo') {
        tattooTerms = matches;
      }
      break;
    }
  }

  if (topicTag !== 'tattoo') {
    tattooTerms = findMatches(text, TOPIC_TERMS.tattoo);
  }

  const isTattooRelated = tattooTerms.length > 0 || topicTag === 'tattoo';
  const intentScore =
    (conversationIntentTerms.length * 3) +
    (localTerms.length * 2) +
    (tattooTerms.length * 2);

  return {
    preview: text.slice(0, 300),
    text,
    conversationIntentTerms,
    localTerms,
    tattooTerms,
    topicTag,
    isTattooRelated,
    intentScore,
  };
}

function detectPlatform(url) {
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    if (hostname.includes('facebook.com')) return 'facebook';
    if (hostname.includes('reddit.com')) return 'reddit';
    if (hostname.includes('instagram.com')) return 'instagram';
    if (hostname.includes('x.com') || hostname.includes('twitter.com')) return 'twitter';
    if (hostname.includes('linkedin.com')) return 'linkedin';
    return hostname;
  } catch {
    return 'unknown';
  }
}

function normalizeFacebookPostUrl(url) {
  if (!url) return null;
  try {
    const parsed = new URL(url, 'https://www.facebook.com');
    if (parsed.hostname.toLowerCase() === 'l.facebook.com' && parsed.pathname === '/l.php') {
      const targetUrl = parsed.searchParams.get('u');
      return targetUrl ? normalizeFacebookPostUrl(targetUrl) : null;
    }

    const hostname = parsed.hostname.toLowerCase();
    if (!hostname.includes('facebook.com')) return null;

    const pathname = parsed.pathname.replace(/\/+$/, '');
    const groupPostMatch = pathname.match(/^\/groups\/([^/]+)\/posts\/([^/]+)$/i);
    if (groupPostMatch) {
      return `https://www.facebook.com/groups/${groupPostMatch[1]}/posts/${groupPostMatch[2]}/`;
    }

    const groupPermalinkMatch = pathname.match(/^\/groups\/([^/]+)\/permalink\/([^/]+)$/i);
    if (groupPermalinkMatch) {
      return `https://www.facebook.com/groups/${groupPermalinkMatch[1]}/permalink/${groupPermalinkMatch[2]}/`;
    }

    const groupRootMatch = pathname.match(/^\/groups\/([^/]+)$/i);
    if (groupRootMatch) {
      const multiPermalinkId = parsed.searchParams.get('multi_permalinks');
      if (multiPermalinkId) {
        return `https://www.facebook.com/groups/${groupRootMatch[1]}/permalink/${multiPermalinkId}/`;
      }

      if (parsed.searchParams.get('view') === 'permalink') {
        const permalinkId = parsed.searchParams.get('id');
        if (permalinkId) {
          return `https://www.facebook.com/groups/${groupRootMatch[1]}/permalink/${permalinkId}/`;
        }
      }
    }

    if (/^\/(permalink|story)\.php$/i.test(pathname)) {
      const storyParamKey = parsed.searchParams.has('story_fbid') ? 'story_fbid' : 'fbid';
      const storyId = parsed.searchParams.get(storyParamKey);
      if (!storyId) return null;

      const clean = new URL(`https://www.facebook.com${/^\/story\.php$/i.test(pathname) ? '/story.php' : '/permalink.php'}`);
      clean.searchParams.set(storyParamKey, storyId);
      const id = parsed.searchParams.get('id');
      if (id) clean.searchParams.set('id', id);
      return clean.toString();
    }

    if (/^\/photo\.php$/i.test(pathname) && parsed.searchParams.get('fbid')) {
      const clean = new URL('https://www.facebook.com/photo.php');
      clean.searchParams.set('fbid', parsed.searchParams.get('fbid'));
      const set = parsed.searchParams.get('set');
      if (set) clean.searchParams.set('set', set);
      return clean.toString();
    }

    if (/^\/[^/]+\/posts\/[^/]+$/i.test(pathname)) {
      return `https://www.facebook.com${pathname}/`;
    }

    return null;
  } catch {
    return null;
  }
}

function buildLeadObject(block, rawPageTitle, rawPageUrl, groupName) {
  const canonicalUrl = block.postUrl
    ? (normalizeFacebookPostUrl(block.postUrl) || block.postUrl)
    : null;

  const source = detectPlatform(canonicalUrl || rawPageUrl) === 'facebook' ? 'facebook_browser' : 'browser_conversation';
  const stableUrl = canonicalUrl || rawPageUrl;
  const itemId = stableUrl
    ? `browser_${Buffer.from(stableUrl).toString('base64').replace(/[^a-zA-Z0-9]/g, '').slice(0, 24)}`
    : `browser_${Buffer.from(block.preview).toString('base64').replace(/[^a-zA-Z0-9]/g, '').slice(0, 24)}`;
  const forum = groupName || rawPageTitle || '';

  return {
    source,
    item_id: itemId,
    url: stableUrl,
    canonical_url: stableUrl,
    title: block.preview,
    snippet: block.preview,
    text: block.text,
    forum,
    created_at: null,
    raw: {
      platform: detectPlatform(canonicalUrl || rawPageUrl),
      kind: 'browser_conversation',
      domain_class: 'social_public',
      topic_tag: block.topicTag,
      is_tattoo_related: block.isTattooRelated,
      intent_score: block.intentScore,
      conversation_intent_terms: block.conversationIntentTerms,
      local_terms: block.localTerms,
      tattoo_terms: block.tattooTerms,
      raw_page_title: rawPageTitle,
      raw_page_url: rawPageUrl,
      raw_post_url_found: Boolean(block.postUrl),
      human_review_only: true,
      group_name: forum,
    }
  };
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} when fetching ${url}`);
  }
  return response.json();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} posting to ${url}: ${text}`);
  }
  return data;
}

function pickInspectablePage(targets, preferredUrl) {
  const pageTargets = targets.filter((target) => target.type === 'page' && target.webSocketDebuggerUrl);
  if (pageTargets.length === 0) return null;
  if (preferredUrl) {
    const exact = pageTargets.find((target) => target.url === preferredUrl);
    if (exact) return exact;
    const normalized = preferredUrl.replace(/\/+$/, '');
    const partial = pageTargets.find((target) => (target.url || '').replace(/\/+$/, '') === normalized);
    if (partial) return partial;
  }
  return pageTargets.find((target) => target.url && target.url !== 'about:blank') || pageTargets[0];
}

class CdpClient {
  constructor(webSocketDebuggerUrl) {
    this.webSocketDebuggerUrl = webSocketDebuggerUrl;
    this.nextId = 1;
    this.pending = new Map();
    this.ws = null;
  }

  async connect() {
    await new Promise((resolve, reject) => {
      const ws = new WebSocket(this.webSocketDebuggerUrl);
      let settled = false;

      ws.addEventListener('open', () => {
        settled = true;
        this.ws = ws;
        resolve();
      });

      ws.addEventListener('message', (event) => {
        try {
          const payload = JSON.parse(String(event.data));
          if (!payload.id) return;
          const pending = this.pending.get(payload.id);
          if (!pending) return;
          this.pending.delete(payload.id);
          if (payload.error) {
            pending.reject(new Error(payload.error.message || JSON.stringify(payload.error)));
            return;
          }
          pending.resolve(payload.result || {});
        } catch (error) {
          if (!settled) {
            settled = true;
            reject(error);
          }
        }
      });

      ws.addEventListener('error', (error) => {
        if (!settled) {
          settled = true;
          reject(error);
        }
      });

      ws.addEventListener('close', () => {
        if (!settled) {
          settled = true;
          reject(new Error('CDP websocket closed before connection was ready.'));
        }
        for (const pending of this.pending.values()) {
          pending.reject(new Error('CDP websocket closed.'));
        }
        this.pending.clear();
      });
    });
  }

  send(method, params = {}) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('CDP websocket is not connected.'));
    }
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async close() {
    if (!this.ws) return;
    const ws = this.ws;
    this.ws = null;
    await new Promise((resolve) => {
      if (ws.readyState === WebSocket.CLOSED) {
        resolve();
        return;
      }
      ws.addEventListener('close', () => resolve(), { once: true });
      ws.close();
    });
  }
}

function extractBlocksOnPage(fallbackPageUrl) {
  const normalize = (text) => (text || '').replace(/\s+/g, ' ').trim();

  const isVisible = (el) => {
    if (!(el instanceof Element)) return false;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  const normalizeFacebookPostUrl = (url) => {
    if (!url) return null;
    try {
      const parsed = new URL(url, 'https://www.facebook.com');
      if (parsed.hostname.toLowerCase() === 'l.facebook.com' && parsed.pathname === '/l.php') {
        const targetUrl = parsed.searchParams.get('u');
        return targetUrl ? normalizeFacebookPostUrl(targetUrl) : null;
      }
      const hostname = parsed.hostname.toLowerCase();
      if (!hostname.includes('facebook.com')) return null;
      const pathname = parsed.pathname.replace(/\/+$/, '');
      const groupPostMatch = pathname.match(/^\/groups\/([^/]+)\/posts\/([^/]+)$/i);
      if (groupPostMatch) return `https://www.facebook.com/groups/${groupPostMatch[1]}/posts/${groupPostMatch[2]}/`;
      const groupPermalinkMatch = pathname.match(/^\/groups\/([^/]+)\/permalink\/([^/]+)$/i);
      if (groupPermalinkMatch) return `https://www.facebook.com/groups/${groupPermalinkMatch[1]}/permalink/${groupPermalinkMatch[2]}/`;
      const groupRootMatch = pathname.match(/^\/groups\/([^/]+)$/i);
      if (groupRootMatch) {
        const multiPermalinkId = parsed.searchParams.get('multi_permalinks');
        if (multiPermalinkId) return `https://www.facebook.com/groups/${groupRootMatch[1]}/permalink/${multiPermalinkId}/`;
        if (parsed.searchParams.get('view') === 'permalink') {
          const permalinkId = parsed.searchParams.get('id');
          if (permalinkId) return `https://www.facebook.com/groups/${groupRootMatch[1]}/permalink/${permalinkId}/`;
        }
      }
      if (/^\/(permalink|story)\.php$/i.test(pathname)) {
        const storyParamKey = parsed.searchParams.has('story_fbid') ? 'story_fbid' : 'fbid';
        const storyId = parsed.searchParams.get(storyParamKey);
        if (!storyId) return null;
        const clean = new URL(`https://www.facebook.com${/^\/story\.php$/i.test(pathname) ? '/story.php' : '/permalink.php'}`);
        clean.searchParams.set(storyParamKey, storyId);
        const id = parsed.searchParams.get('id');
        if (id) clean.searchParams.set('id', id);
        return clean.toString();
      }
      if (/^\/photo\.php$/i.test(pathname) && parsed.searchParams.get('fbid')) {
        const clean = new URL('https://www.facebook.com/photo.php');
        clean.searchParams.set('fbid', parsed.searchParams.get('fbid'));
        const set = parsed.searchParams.get('set');
        if (set) clean.searchParams.set('set', set);
        return clean.toString();
      }
      if (/^\/[^/]+\/posts\/[^/]+$/i.test(pathname)) return `https://www.facebook.com${pathname}/`;
      return null;
    } catch {
      return null;
    }
  };

  const looksLikeTimestamp = (value) => {
    const normalizedValue = normalize(value).toLowerCase();
    if (!normalizedValue) return false;
    return (
      /^\d+\s*(s|sec|secs|m|min|mins|h|hr|hrs|d|day|days|w|wk|wks|mo|mos|y|yr|yrs)$/.test(normalizedValue) ||
      /^(just now|now|today|yesterday)$/i.test(normalizedValue) ||
      /^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\b/.test(normalizedValue) ||
      /^(mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b/.test(normalizedValue) ||
      normalizedValue.includes(' at ')
    );
  };

  const extractFacebookPostUrlFromNode = (node) => {
    const anchors = Array.from(node.querySelectorAll('a[href]'));
    const candidatesByUrl = new Map();
    for (const anchor of anchors) {
      const href = anchor.getAttribute('href') || '';
      const ariaLabel = normalize(anchor.getAttribute('aria-label') || '').toLowerCase();
      const title = normalize(anchor.getAttribute('title') || '').toLowerCase();
      const text = normalize(anchor.textContent || '').toLowerCase();
      const normalized = normalizeFacebookPostUrl(href);
      if (!normalized) continue;
      let score = 0;
      if (ariaLabel.includes('full story') || ariaLabel.includes('see more') || ariaLabel.includes('view post')) score += 5;
      if (title.includes('full story') || title.includes('see more') || title.includes('view post')) score += 5;
      if (text === 'full story' || text === 'see more' || text === 'view post') score += 5;
      if (looksLikeTimestamp(ariaLabel) || looksLikeTimestamp(title) || looksLikeTimestamp(text)) score += 8;
      if (href.includes('/groups/') && href.includes('/permalink/')) score += 8;
      if (href.includes('/groups/') && href.includes('/posts/')) score += 7;
      if (href.includes('multi_permalinks=')) score += 7;
      if (href.includes('view=permalink')) score += 7;
      if (href.includes('story.php')) score += 6;
      if (href.includes('permalink.php')) score += 6;
      if (href.includes('photo.php')) score += 5;
      const existing = candidatesByUrl.get(normalized);
      if (!existing || score > existing.score) candidatesByUrl.set(normalized, { url: normalized, score });
    }
    const candidates = Array.from(candidatesByUrl.values());
    candidates.sort((a, b) => b.score - a.score);
    return candidates[0]?.url || null;
  };

  const candidateSelectors = ['article', '[role="article"]', '[role="listitem"]', 'li', 'section', 'main > div > div', 'div[data-testid]', 'div'];
  const seen = new Set();
  const results = [];
  const isFacebook = window.location.hostname.toLowerCase().includes('facebook.com');

  for (const selector of candidateSelectors) {
    const nodes = Array.from(document.querySelectorAll(selector));
    for (const node of nodes) {
      if (results.length >= 10) break;
      if (!isVisible(node)) continue;
      const text = normalize(node.innerText || '');
      if (text.length < 80 || text.length > 4000) continue;
      const rect = node.getBoundingClientRect();
      const signature = `${text.slice(0, 120)}|${Math.round(rect.top)}|${Math.round(rect.height)}`;
      if (seen.has(signature)) continue;
      seen.add(signature);
      results.push({ text, postUrl: isFacebook ? extractFacebookPostUrlFromNode(node) : fallbackPageUrl });
    }
    if (results.length >= 10) break;
  }

  return { pageTitle: document.title, pageUrl: window.location.href, blocks: results };
}

async function evaluateOnPage(target, expression) {
  const client = new CdpClient(target.webSocketDebuggerUrl);
  await client.connect();
  try {
    await client.send('Runtime.enable');
    const result = await client.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    return result.result?.value;
  } finally {
    await client.close();
  }
}

async function openTargetForUrl(url) {
  const response = await fetch(`${cdpUrl}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} when opening ${url} via Chrome DevTools`);
  }
  return response.json();
}

async function closeTargetById(targetId) {
  if (!targetId) return;
  await fetch(`${cdpUrl}/json/close/${targetId}`);
}

async function scanTarget(targetConfig) {
  let openedTarget = null;
  try {
    openedTarget = await openTargetForUrl(targetConfig.url);
  } catch (error) {
    throw new Error(`Could not open target ${targetConfig.url}: ${String(error)}`);
  }

  await new Promise((resolve) => setTimeout(resolve, 2500));

  const targets = await fetchJson(`${cdpUrl}/json/list`);
  const target = pickInspectablePage(targets, targetConfig.url) || openedTarget;
  if (!target || !target.webSocketDebuggerUrl) {
    throw new Error(`No inspectable Chrome tab found for ${targetConfig.url}`);
  }

  const fallbackPageUrl = target.url || targetConfig.url;
  const expression = `(${extractBlocksOnPage.toString()})(${JSON.stringify(fallbackPageUrl)})`;
  const pageState = await evaluateOnPage(target, expression);
  const pageTitle = pageState?.pageTitle || target.title || targetConfig.name || '';
  const pageUrl = pageState?.pageUrl || fallbackPageUrl;
  const blocks = Array.isArray(pageState?.blocks) ? pageState.blocks : [];
  const classified = blocks.map((block) => ({ ...classifyBlock(block.text), postUrl: block.postUrl }));
  const filtered = classified.filter((block) => block.isTattooRelated || block.intentScore >= 5);
  const leads = filtered.map((block) => buildLeadObject(block, pageTitle, pageUrl, targetConfig.name));

  await closeTargetById(openedTarget?.id);
  return { target: targetConfig, pageTitle, pageUrl, leads };
}

async function main() {
  try {
    await fetchJson(`${cdpUrl}/json/version`);
  } catch (error) {
    console.error(`Chrome DevTools not reachable at ${cdpUrl}`);
    console.error('Start Chrome on the Mac with remote debugging on port 9222, then rerun the scan.');
    console.error(String(error));
    process.exit(1);
  }

  const allLeads = [];
  const summaries = [];
  for (const targetConfig of groupTargets) {
    try {
      const result = await scanTarget(targetConfig);
      allLeads.push(...result.leads);
      summaries.push({ group: targetConfig.name, url: targetConfig.url, leads: result.leads.length });
    } catch (error) {
      console.error(`Scan failed for ${targetConfig.url}`);
      console.error(String(error));
      summaries.push({ group: targetConfig.name, url: targetConfig.url, error: String(error) });
    }
  }

  fs.writeFileSync(outputPath, JSON.stringify(allLeads, null, 2));

  if (scanMode === 'post') {
    const response = await postJson(endpointUrl, { items: allLeads });
    console.log(JSON.stringify({ posted: true, endpoint: endpointUrl, summary: summaries, ingest: response }, null, 2));
  } else {
    console.log(JSON.stringify({ posted: false, summary: summaries, items: allLeads }, null, 2));
    console.log(`\nWrote ${allLeads.length} lead object(s) to ${outputPath}`);
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(String(error));
    process.exit(1);
  });
}

module.exports = {
  normalizeFacebookPostUrl,
  buildLeadObject,
  detectPlatform,
  parseGroupTargets,
};
