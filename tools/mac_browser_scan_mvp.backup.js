#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const apiBaseUrl = process.env.BIS_API_BASE_URL || 'http://127.0.0.1:8787';
const inputPath = path.join(__dirname, 'mac_browser_scan_output.json');
const endpointUrl = `${apiBaseUrl.replace(/\/$/, '')}/admin/ingest-browser-items`;

async function main() {
  if (!fs.existsSync(inputPath)) {
    console.error(`Input file not found: ${inputPath}`);
    console.error('Run the local JSON-generation step first so mac_browser_scan_output.json exists.');
    process.exit(1);
  }

  const raw = fs.readFileSync(inputPath, 'utf8');
  let leads;
  try {
    leads = JSON.parse(raw);
  } catch (error) {
    console.error(`Failed to parse JSON from ${inputPath}`);
    console.error(String(error));
    process.exit(1);
  }

  if (!Array.isArray(leads)) {
    console.error('Expected mac_browser_scan_output.json to contain a JSON array.');
    process.exit(1);
  }

  if (leads.length === 0) {
    console.log('No lead objects found in mac_browser_scan_output.json');
    process.exit(0);
  }

  const items = leads.map((lead, index) => {
    const text = lead.text || lead.snippet || '';
    const title = lead.title || (text ? text.slice(0, 120) : `browser lead ${index + 1}`);
    const url = lead.url || lead.raw_page_url || '';
    const itemIdSource = [
      lead.source || 'browser_conversation',
      lead.platform || '',
      url,
      title,
      text.slice(0, 500)
    ].join('|');

    return {
      source: lead.source || 'browser_conversation',
      item_id: stableId(itemIdSource),
      url,
      canonical_url: url,
      title,
      snippet: lead.snippet || text.slice(0, 300),
      text,
      forum: lead.raw_page_title || null,
      created_at: null,
      raw: {
        kind: 'browser_conversation',
        platform: lead.platform || 'unknown',
        topic_tag: lead.topic_tag || 'other',
        is_tattoo_related: Boolean(lead.is_tattoo_related),
        intent_score: Number(lead.intent_score || 0),
        conversation_intent_terms: Array.isArray(lead.conversation_intent_terms) ? lead.conversation_intent_terms : [],
        local_terms: Array.isArray(lead.local_terms) ? lead.local_terms : [],
        tattoo_terms: Array.isArray(lead.tattoo_terms) ? lead.tattoo_terms : [],
        raw_page_title: lead.raw_page_title || null,
        raw_page_url: lead.raw_page_url || url || null,
        human_review_only: true
      }
    };
  });

  const response = await fetch(endpointUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ items })
  });

  const responseText = await response.text();

  console.log(`POST ${endpointUrl}`);
  console.log(`HTTP ${response.status}`);

  if (!response.ok) {
    console.error(responseText);
    process.exit(1);
  }

  try {
    console.log(JSON.stringify(JSON.parse(responseText), null, 2));
  } catch {
    console.log(responseText);
  }
}

function stableId(input) {
  let hash = 2166136261;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return `browser_${(hash >>> 0).toString(16)}`;
}

main().catch((error) => {
  console.error(String(error));
  process.exit(1);
});
