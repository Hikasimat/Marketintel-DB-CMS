"""Interactive developer and QA testing console for headless CMS backend."""

# ruff: noqa: E501

from __future__ import annotations

from django.http import HttpRequest, HttpResponse

CONSOLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CMS Backend — Interactive Testing Console</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-dark: #0a0e17;
      --bg-card: rgba(17, 24, 39, 0.85);
      --bg-input: #1f2937;
      --border: rgba(55, 65, 81, 0.7);
      --border-accent: rgba(99, 102, 241, 0.4);
      --primary: #6366f1;
      --primary-hover: #4f46e5;
      --accent-cyan: #06b6d4;
      --accent-emerald: #10b981;
      --accent-amber: #f59e0b;
      --accent-rose: #f43f5e;
      --text: #f9fafb;
      --text-muted: #9ca3af;
      --text-dim: #6b7280;
      --mono: 'JetBrains Mono', monospace;
      --sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: var(--sans);
      background: radial-gradient(circle at 10% 10%, rgba(99, 102, 241, 0.08) 0%, transparent 40%),
                  radial-gradient(circle at 90% 90%, rgba(6, 182, 212, 0.08) 0%, transparent 40%),
                  var(--bg-dark);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    /* Top Navigation Header */
    header {
      background: rgba(15, 23, 42, 0.85);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid var(--border);
      padding: 0.85rem 1.75rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .logo-group {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .logo-badge {
      background: linear-gradient(135deg, var(--primary), var(--accent-cyan));
      width: 34px;
      height: 34px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 1.1rem;
      color: white;
      box-shadow: 0 4px 12px rgba(99, 102, 241, 0.35);
    }
    .brand-title {
      font-weight: 700;
      font-size: 1.15rem;
      letter-spacing: -0.02em;
      background: linear-gradient(120deg, #fff, #9ca3af);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .brand-sub {
      font-size: 0.75rem;
      color: var(--accent-cyan);
      background: rgba(6, 182, 212, 0.1);
      padding: 2px 8px;
      border-radius: 9999px;
      border: 1px solid rgba(6, 182, 212, 0.3);
      font-weight: 600;
      margin-left: 0.5rem;
    }

    .header-status {
      display: flex;
      align-items: center;
      gap: 1.25rem;
      font-size: 0.85rem;
    }
    .status-pill {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      background: rgba(31, 41, 55, 0.6);
      padding: 0.35rem 0.75rem;
      border-radius: 9999px;
      border: 1px solid var(--border);
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-emerald);
      box-shadow: 0 0 8px var(--accent-emerald);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { opacity: 1; }
      50% { opacity: 0.4; }
      100% { opacity: 1; }
    }

    /* Main Layout */
    .layout {
      display: grid;
      grid-template-columns: 240px 1fr 380px;
      flex: 1;
      overflow: hidden;
      height: calc(100vh - 65px);
    }

    /* Sidebar Navigation */
    .sidebar {
      background: rgba(15, 23, 42, 0.5);
      border-right: 1px solid var(--border);
      padding: 1.25rem 0.75rem;
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
    }
    .nav-btn {
      display: flex;
      align-items: center;
      gap: 0.65rem;
      padding: 0.65rem 0.9rem;
      border-radius: 8px;
      color: var(--text-muted);
      background: transparent;
      border: 1px solid transparent;
      font-size: 0.88rem;
      font-weight: 500;
      cursor: pointer;
      text-align: left;
      transition: all 0.18s ease;
      width: 100%;
    }
    .nav-btn:hover {
      color: var(--text);
      background: rgba(31, 41, 55, 0.6);
      border-color: var(--border);
    }
    .nav-btn.active {
      color: #fff;
      background: linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(6, 182, 212, 0.1));
      border-color: var(--primary);
      box-shadow: 0 2px 8px rgba(99, 102, 241, 0.2);
    }
    .nav-btn .icon { font-size: 1.1rem; }

    /* Content Area */
    .content-area {
      overflow-y: auto;
      padding: 1.5rem 2rem;
      background: transparent;
    }
    .tab-content { display: none; }
    .tab-content.active { display: block; animation: fadeIn 0.2s ease; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

    /* Cards */
    .card {
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    }
    .card-title {
      font-size: 1.1rem;
      font-weight: 600;
      margin-bottom: 0.4rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .card-desc {
      font-size: 0.84rem;
      color: var(--text-muted);
      margin-bottom: 1.25rem;
    }

    /* Forms & Inputs */
    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
      margin-bottom: 1rem;
    }
    .form-group {
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
    }
    .form-label {
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-muted);
    }
    input, select, textarea {
      background: var(--bg-input);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.65rem 0.85rem;
      color: var(--text);
      font-family: var(--sans);
      font-size: 0.88rem;
      transition: all 0.15s ease;
      width: 100%;
    }
    input:focus, select:focus, textarea:focus {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
    }
    textarea { font-family: var(--mono); font-size: 0.82rem; resize: vertical; }

    /* Buttons */
    .btn {
      background: var(--primary);
      color: white;
      border: none;
      border-radius: 8px;
      padding: 0.65rem 1.25rem;
      font-size: 0.88rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.45rem;
      transition: all 0.18s ease;
    }
    .btn:hover { background: var(--primary-hover); transform: translateY(-1px); }
    .btn:active { transform: translateY(0); }
    .btn-secondary {
      background: rgba(31, 41, 55, 0.8);
      color: var(--text);
      border: 1px solid var(--border);
    }
    .btn-secondary:hover { background: rgba(55, 65, 81, 0.9); }
    .btn-success { background: var(--accent-emerald); }
    .btn-success:hover { background: #059669; }
    .btn-danger { background: var(--accent-rose); }
    .btn-danger:hover { background: #e11d48; }

    /* Live Activity Inspector Panel (Right Drawer) */
    .inspector {
      background: rgba(15, 23, 42, 0.92);
      border-left: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .inspector-header {
      padding: 0.85rem 1.25rem;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.88rem;
      font-weight: 600;
    }
    .inspector-badge {
      font-size: 0.72rem;
      background: rgba(99, 102, 241, 0.15);
      color: var(--accent-cyan);
      padding: 2px 7px;
      border-radius: 4px;
      font-family: var(--mono);
    }
    .inspector-body {
      flex: 1;
      padding: 1rem;
      overflow-y: auto;
      font-family: var(--mono);
      font-size: 0.78rem;
    }
    .log-item {
      background: rgba(31, 41, 55, 0.6);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.65rem 0.75rem;
      margin-bottom: 0.75rem;
    }
    .log-meta {
      display: flex;
      justify-content: space-between;
      margin-bottom: 0.35rem;
    }
    .badge-method {
      padding: 1px 6px;
      border-radius: 4px;
      font-weight: 700;
      font-size: 0.7rem;
    }
    .badge-get { background: rgba(16, 185, 129, 0.2); color: var(--accent-emerald); }
    .badge-post { background: rgba(99, 102, 241, 0.2); color: var(--primary); }
    .badge-delete { background: rgba(244, 63, 94, 0.2); color: var(--accent-rose); }
    .badge-patch { background: rgba(245, 158, 11, 0.2); color: var(--accent-amber); }
    .status-code { font-weight: 600; }
    .code-200 { color: var(--accent-emerald); }
    .code-400 { color: var(--accent-rose); }
    pre {
      background: #090d16;
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 6px;
      padding: 0.5rem;
      overflow-x: auto;
      color: #e2e8f0;
      white-space: pre-wrap;
      word-break: break-all;
    }

    /* Stat Cards */
    .stats-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 0.75rem;
      margin-bottom: 1.25rem;
    }
    .stat-card {
      background: rgba(31, 41, 55, 0.45);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.85rem;
      text-align: center;
    }
    .stat-val { font-size: 1.5rem; font-weight: 700; color: #fff; margin-bottom: 0.2rem; }
    .stat-label { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; }

    /* Tables */
    .table-container {
      overflow-x: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.85rem;
    }
    th {
      background: rgba(31, 41, 55, 0.8);
      padding: 0.65rem 0.9rem;
      font-weight: 600;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
    }
    td {
      padding: 0.75rem 0.9rem;
      border-bottom: 1px solid var(--border);
      color: var(--text);
    }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: rgba(255, 255, 255, 0.02); }
  </style>
</head>
<body>

  <!-- Top Navigation Header -->
  <header>
    <div class="logo-group">
      <div class="logo-badge">C</div>
      <div>
        <span class="brand-title">CMS Headless Backend</span>
        <span class="brand-sub">QA Console</span>
      </div>
    </div>

    <div class="header-status">
      <div class="status-pill" id="healthPill">
        <span class="status-dot" id="healthDot"></span>
        <span id="healthText">Probing Health...</span>
      </div>
      <div class="status-pill">
        <span style="color:var(--text-dim)">User:</span>
        <strong id="headerUserEmail" style="color:var(--accent-cyan); margin-left:4px">Not Logged In</strong>
      </div>
      <a href="/api/v1/docs/" target="_blank" class="btn btn-secondary" style="font-size:0.78rem; padding:0.35rem 0.75rem">
        Swagger Docs ↗
      </a>
    </div>
  </header>

  <div class="layout">

    <!-- Sidebar Navigation -->
    <nav class="sidebar">
      <button class="nav-btn active" onclick="switchTab('auth')">
        <span class="icon">🔑</span> Auth & JWT
      </button>
      <button class="nav-btn" onclick="switchTab('tenancy')">
        <span class="icon">🏢</span> Workspaces & Sites
      </button>
      <button class="nav-btn" onclick="switchTab('content')">
        <span class="icon">📝</span> Content & Articles
      </button>
      <button class="nav-btn" onclick="switchTab('seo')">
        <span class="icon">🔍</span> SEO & Sitemaps
      </button>
      <button class="nav-btn" onclick="switchTab('analytics')">
        <span class="icon">📊</span> Privacy Analytics
      </button>
      <button class="nav-btn" onclick="switchTab('consent')">
        <span class="icon">🛡️</span> Consent Manager
      </button>
      <button class="nav-btn" onclick="switchTab('github')">
        <span class="icon">🐙</span> GitHub Integration
      </button>
    </nav>

    <!-- Main Content Area -->
    <main class="content-area">

      <!-- TAB 1: AUTH & JWT -->
      <section id="tab-auth" class="tab-content active">
        <div class="card">
          <h2 class="card-title">🔑 Authentication & Token Management</h2>
          <p class="card-desc">Login with administrative or workspace credentials to generate JWT access tokens (pure-Python RS256/HS256).</p>

          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">Email</label>
              <input type="email" id="authEmail" value="admin@cms.local">
            </div>
            <div class="form-group">
              <label class="form-label">Password</label>
              <input type="password" id="authPassword" value="AdminPassword123!">
            </div>
          </div>
          <div style="display:flex; gap:0.75rem; margin-top:0.5rem">
            <button class="btn" onclick="login()">Login & Obtain Tokens</button>
            <button class="btn btn-secondary" onclick="fetchMe()">Verify /auth/me/</button>
            <button class="btn btn-danger" onclick="logout()">Logout</button>
          </div>
        </div>

        <div class="card">
          <h3 class="card-title">Active JWT Access Token</h3>
          <p class="card-desc">Token automatically attached to subsequent API requests as <code>Authorization: Bearer &lt;token&gt;</code>.</p>
          <pre id="tokenDisplay" style="max-height:120px">No active token. Click "Login" above.</pre>
          <div style="margin-top:0.75rem">
            <button class="btn btn-secondary" onclick="copyToken()">Copy Token for Swagger</button>
          </div>
        </div>
      </section>

      <!-- TAB 2: WORKSPACES & SITES -->
      <section id="tab-tenancy" class="tab-content">
        <div class="card">
          <h2 class="card-title">🏢 Workspace & Multi-Tenancy</h2>
          <p class="card-desc">Manage tenant workspaces and registered web publication sites.</p>

          <div style="display:flex; gap:0.75rem; margin-bottom:1.25rem">
            <button class="btn btn-secondary" onclick="loadWorkspaces()">Refresh Workspaces</button>
            <button class="btn btn-secondary" onclick="loadSites()">Refresh Sites</button>
          </div>

          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">Selected Workspace</label>
              <select id="workspaceSelect" onchange="loadSites()"><option value="">Logging in...</option></select>
            </div>
            <div class="form-group">
              <label class="form-label">Selected Site</label>
              <select id="siteSelect"><option value="">Logging in...</option></select>
            </div>
          </div>
        </div>

        <div class="card">
          <h3 class="card-title">Create New Publication Site</h3>
          <p class="card-desc">Register a new publication under the selected tenant workspace.</p>
          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">Site Name</label>
              <input type="text" id="newSiteName" placeholder="Tech Crunch Daily">
            </div>
            <div class="form-group">
              <label class="form-label">Slug</label>
              <input type="text" id="newSiteSlug" placeholder="tech-crunch-daily">
            </div>
            <div class="form-group">
              <label class="form-label">Default Locale</label>
              <input type="text" id="newSiteLocale" value="en-US">
            </div>
          </div>
          <button class="btn btn-success" onclick="createSite()">Create Site</button>
        </div>
      </section>

      <!-- TAB 3: CONTENT & ARTICLES -->
      <section id="tab-content" class="tab-content">
        <div class="card">
          <h2 class="card-title">📝 Content Publishing & Revisions</h2>
          <p class="card-desc">Author, version, and publish articles to the public delivery API.</p>

          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">Article Title</label>
              <input type="text" id="artTitle" value="Next-Gen AI Agents in Production">
            </div>
            <div class="form-group">
              <label class="form-label">Slug</label>
              <input type="text" id="artSlug" value="next-gen-ai-agents">
            </div>
          </div>
          <div class="form-group" style="margin-bottom:1rem">
            <label class="form-label">Body Content (Markdown or HTML)</label>
            <textarea id="artBody" rows="4"># Next-Gen AI Agents\n\nAutonomous agentic workflows represent the future of software development.</textarea>
          </div>
          <div style="display:flex; flex-wrap:wrap; gap:0.75rem">
            <button class="btn btn-primary" onclick="createArticle()">Create Draft Article</button>
            <button class="btn btn-secondary" onclick="loadArticles()">List Workspace Articles</button>
            <button class="btn btn-secondary" onclick="viewPublicDelivery()">Compare With Public Delivery API</button>
          </div>
        </div>

        <div class="card" id="articlesTableCard">
          <h3 class="card-title">Articles for Active Site</h3>
          <p class="card-desc">Draft articles are securely isolated inside your workspace backend. Only published articles appear on the public delivery API.</p>
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Slug</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody id="articlesTableBody">
                <tr><td colspan="4" style="text-align:center; color:var(--text-dim)">Click "List Workspace Articles" to fetch.</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- TAB 4: SEO & SITEMAPS -->
      <section id="tab-seo" class="tab-content">
        <div class="card">
          <h2 class="card-title">🔍 Search Engine Optimization & Previews</h2>
          <p class="card-desc">Canonical link relations, title formats, robots.txt, and dynamic XML sitemaps.</p>

          <div style="display:flex; gap:0.75rem; margin-bottom:1.25rem">
            <button class="btn btn-secondary" onclick="previewSitemap()">Preview Dynamic Sitemap.xml</button>
            <button class="btn btn-secondary" onclick="previewRobots()">Preview Robots.txt</button>
          </div>
          <pre id="seoPreviewDisplay" style="max-height:220px">Click one of the preview buttons above to view output.</pre>
        </div>

        <div class="card">
          <h3 class="card-title">🔍 Search Console & Indexing Providers (Google & Bing)</h3>
          <p class="card-desc">Google Indexing API and IndexNow real-time crawl submissions.</p>

          <div style="display:flex; flex-wrap:wrap; gap:0.6rem; margin-bottom:1rem">
            <button class="btn btn-secondary" onclick="checkSearchProviders()">Check Configured Providers</button>
            <button class="btn btn-secondary" onclick="inspectIndexNowKey()">Inspect IndexNow Key</button>
            <button class="btn btn-secondary" onclick="viewIndexingLogs()">View Submission Logs</button>
          </div>

          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">Provider</label>
              <select id="indexingProvider">
                <option value="GOOGLE">Google Search Console</option>
                <option value="BING">Bing Webmaster (IndexNow)</option>
                <option value="INDEXNOW">IndexNow Protocol</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">URL To Submit For Indexing</label>
              <input type="url" id="indexingUrl" value="https://techradar.io/articles/future-of-autonomous-ai-agents">
            </div>
          </div>
          <button class="btn btn-primary" onclick="submitUrlForIndexing()">Submit URL for Indexing</button>
        </div>
      </section>

      <!-- TAB 5: ANALYTICS SIMULATOR -->
      <section id="tab-analytics" class="tab-content">
        <div class="card">
          <h2 class="card-title">📊 Privacy-Preserving First-Party Analytics</h2>
          <p class="card-desc">Zero raw IP address storage. Coarsened User-Agents. Pseudonymous visitor telemetry.</p>

          <div class="stats-row">
            <div class="stat-card">
              <div class="stat-val" id="statEvents">0</div>
              <div class="stat-label">Events</div>
            </div>
            <div class="stat-card">
              <div class="stat-val" id="statVisitors">0</div>
              <div class="stat-label">Visitors</div>
            </div>
            <div class="stat-card">
              <div class="stat-val" id="statViews">0</div>
              <div class="stat-label">Page Views</div>
            </div>
            <div class="stat-card">
              <div class="stat-val" id="statClicks">0</div>
              <div class="stat-label">CTA Clicks</div>
            </div>
          </div>

          <h3 style="font-size:0.95rem; margin-bottom:0.75rem">Simulate Inbound Event Stream:</h3>
          <div style="display:flex; flex-wrap:wrap; gap:0.6rem; margin-bottom:1rem">
            <button class="btn btn-secondary" onclick="ingestEvent('page_view', '/blog/post-1')">Simulate Page View</button>
            <button class="btn btn-secondary" onclick="ingestEvent('cta_click', '/pricing')">Simulate CTA Click</button>
            <button class="btn btn-secondary" onclick="ingestEvent('form_submit', '/contact')">Simulate Form Submit</button>
            <button class="btn btn-primary" onclick="loadAnalyticsMetrics()">Fetch Aggregated Metrics</button>
          </div>
        </div>

        <div class="card">
          <h3 class="card-title">📈 Google Analytics 4 (GA4) Integration</h3>
          <p class="card-desc">OAuth token synchronization and server-side GA4 reporting.</p>
          <div style="display:flex; flex-wrap:wrap; gap:0.6rem">
            <button class="btn btn-secondary" onclick="checkAnalyticsConfig()">Check Site Analytics Config</button>
            <button class="btn btn-secondary" onclick="connectGA4Mock()">Connect GA4 Property</button>
            <button class="btn btn-primary" onclick="fetchGA4Report()">Fetch GA4 Live Report</button>
          </div>
        </div>
      </section>

      <!-- TAB 6: CONSENT MANAGEMENT -->
      <section id="tab-consent" class="tab-content">
        <div class="card">
          <h2 class="card-title">🛡️ Cookie & Privacy Consent Manager</h2>
          <p class="card-desc">GDPR Art. 7 compliant records, Google Consent Mode (GCM v2) mappings, and right-to-withdraw enforcement.</p>

          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">Simulated Visitor ID</label>
              <input type="text" id="consentVisitorId" value="visitor-anon-test-101">
            </div>
            <div class="form-group">
              <label class="form-label">Jurisdiction</label>
              <select id="consentJurisdiction">
                <option value="EU_GDPR">EU (GDPR Strict Opt-In)</option>
                <option value="US_CCPA">US (CCPA Opt-Out)</option>
                <option value="GLOBAL">Global / Default</option>
              </select>
            </div>
          </div>

          <div style="display:flex; gap:0.75rem; margin-top:0.5rem">
            <button class="btn btn-success" onclick="recordConsent(true, true)">Grant All (Analytics + Ads)</button>
            <button class="btn btn-secondary" onclick="recordConsent(true, false)">Analytics Only</button>
            <button class="btn btn-danger" onclick="recordConsent(false, false)">Reject Non-Essential</button>
          </div>
        </div>
      </section>

      <!-- TAB 7: GITHUB INTEGRATION -->
      <section id="tab-github" class="tab-content">
        <div class="card">
          <h2 class="card-title">🐙 GitHub App Integration Status</h2>
          <p class="card-desc">Authorized GitHub App, repository inspection, framework detection, and non-destructive PR generation.</p>

          <div class="stats-row">
            <div class="stat-card">
              <div class="stat-val" style="color:var(--accent-emerald)">ACTIVE</div>
              <div class="stat-label">App Status</div>
            </div>
            <div class="stat-card">
              <div class="stat-val" style="color:var(--accent-cyan)">5509577</div>
              <div class="stat-label">App ID</div>
            </div>
            <div class="stat-card">
              <div class="stat-val" style="color:var(--accent-emerald)">LOADED</div>
              <div class="stat-label">RSA Private Key</div>
            </div>
          </div>

          <div style="display:flex; flex-wrap:wrap; gap:0.75rem; margin-top:0.5rem">
            <a href="https://github.com/apps/cms-integration" target="_blank" class="btn btn-secondary" style="text-decoration:none">
              Open App on GitHub (Install / Manage) ↗
            </a>
            <button class="btn btn-secondary" onclick="fetchInstallations()">List Authorized Installations</button>
          </div>
        </div>

        <div class="card">
          <h3 class="card-title">📂 Inspect Accessible Repositories</h3>
          <p class="card-desc">Query repositories granted to your GitHub App installation.</p>
          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">Installation ID</label>
              <input type="number" id="ghInstallationId" value="12345" placeholder="e.g. 12345 or from installations list">
            </div>
          </div>
          <div style="display:flex; gap:0.75rem">
            <button class="btn btn-primary" onclick="fetchAccessibleRepos()">Fetch Accessible Repositories</button>
          </div>
          <div id="repoListDisplay" style="margin-top:1rem"></div>
        </div>

        <div class="card">
          <h3 class="card-title">🔗 Connect Repository & Run Automation</h3>
          <p class="card-desc">Link a repository to active site, detect framework (Next.js/Vite/Astro), and create integration PR.</p>
          <div class="form-grid">
            <div class="form-group">
              <label class="form-label">Repository Full Name</label>
              <input type="text" id="ghRepoFullName" value="acme-corp/nextjs-frontend" placeholder="owner/repo">
            </div>
            <div class="form-group">
              <label class="form-label">Base Branch</label>
              <input type="text" id="ghBaseBranch" value="main">
            </div>
          </div>
          <div style="display:flex; flex-wrap:wrap; gap:0.75rem">
            <button class="btn btn-secondary" onclick="connectRepoToSite()">Connect Repo to Site</button>
            <button class="btn btn-secondary" onclick="analyzeConnectedRepo()">Detect Framework</button>
            <button class="btn btn-success" onclick="openIntegrationPR()">Open Integration PR</button>
          </div>
        </div>
      </section>

    </main>

    <!-- Right-Hand Realtime API Inspector Drawer -->
    <aside class="inspector">
      <div class="inspector-header">
        <span>Activity Inspector</span>
        <span class="inspector-badge" id="latencyBadge">READY</span>
      </div>
      <div class="inspector-body" id="inspectorLog">
        <div style="color:var(--text-dim); text-align:center; padding-top:2rem;">
          API calls made from this console will stream live here.
        </div>
      </div>
    </aside>

  </div>

  <script>
    let authToken = localStorage.getItem('cms_jwt_token') || '';
    let currentWorkspaces = [];
    let currentSites = [];

    // Switch Tabs
    function switchTab(tabId) {
      document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
      document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
      const target = document.getElementById(`tab-${tabId}`);
      if (target) target.classList.add('active');
      event.currentTarget.classList.add('active');
    }

    // Health Probe
    async function checkHealth() {
      const dot = document.getElementById('healthDot');
      const text = document.getElementById('healthText');
      try {
        const res = await fetch('/health/live');
        if (res.ok) {
          dot.style.background = '#10b981';
          dot.style.boxShadow = '0 0 8px #10b981';
          text.textContent = 'Backend Active (200 OK)';
        } else {
          throw new Error('Unhealthy');
        }
      } catch (err) {
        dot.style.background = '#f43f5e';
        dot.style.boxShadow = '0 0 8px #f43f5e';
        text.textContent = 'Backend Offline';
      }
    }
    setInterval(checkHealth, 15000);
    checkHealth();

    // Central API Fetch Wrapper with Realtime Logging
    async function apiCall(method, path, body = null, requireAuth = true) {
      // Ensure we have a session before any authenticated call
      if (requireAuth && !authToken) {
        await login(true);
      }
      // Refuse to call endpoints with missing workspace/site IDs
      if (['/workspaces//', '/sites//', 'undefined', 'Loading...'].some(bad => path.includes(bad))) {
        alert('Select a Workspace and Site first (Workspaces & Sites tab). If the lists are empty, click Login in the Auth tab.');
        return { status: 0, ok: false, data: { error: 'Missing workspace/site selection' } };
      }
      const startTime = performance.now();
      const headers = { 'Content-Type': 'application/json' };
      if (requireAuth && authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
      }

      const options = { method, headers };
      if (body && method !== 'GET') {
        options.body = JSON.stringify(body);
      }

      let res, data;
      try {
        res = await fetch(path, options);
        const text = await res.text();
        try {
          data = JSON.parse(text);
        } catch {
          data = text;
        }

        // Automatic transparent token refresh on token_expired
        if (res.status === 401 && requireAuth && data && data.error && data.error.code === 'token_expired') {
          const email = document.getElementById('authEmail')?.value || 'admin@cms.local';
          const password = document.getElementById('authPassword')?.value || 'AdminPassword123!';
          const reloginRes = await fetch('/api/v1/auth/login/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
          });
          if (reloginRes.ok) {
            const reloginData = await reloginRes.json();
            if (reloginData.access) {
              authToken = reloginData.access;
              localStorage.setItem('cms_jwt_token', authToken);
              document.getElementById('tokenDisplay').textContent = authToken;
              headers['Authorization'] = `Bearer ${authToken}`;
              res = await fetch(path, options);
              const retryText = await res.text();
              try { data = JSON.parse(retryText); } catch { data = retryText; }
            }
          }
        }
      } catch (err) {
        data = { error: err.message };
        res = { status: 500, ok: false };
      }

      const elapsed = Math.round(performance.now() - startTime);
      logActivity(method, path, res.status, elapsed, data);
      return { status: res.status, ok: res.ok, data };
    }

    // Activity Log Stream
    function logActivity(method, path, status, latency, data) {
      const container = document.getElementById('inspectorLog');
      const badgeClass = `badge-${method.toLowerCase()}`;
      const statusClass = status >= 200 && status < 300 ? 'code-200' : 'code-400';

      const item = document.createElement('div');
      item.className = 'log-item';
      item.innerHTML = `
        <div class="log-meta">
          <div>
            <span class="badge-method ${badgeClass}">${method}</span>
            <span style="color:var(--text); font-weight:600; margin-left:4px">${path}</span>
          </div>
          <div>
            <span class="status-code ${statusClass}">${status}</span>
            <span style="color:var(--text-dim); margin-left:4px">${latency}ms</span>
          </div>
        </div>
        <pre>${typeof data === 'object' ? JSON.stringify(data, null, 2) : data}</pre>
      `;

      if (container.children.length === 1 && container.children[0].tagName === 'DIV' && container.children[0].innerText.includes('stream live')) {
        container.innerHTML = '';
      }
      container.insertBefore(item, container.firstChild);
      document.getElementById('latencyBadge').textContent = `${latency}ms`;
    }

    // Auth Operations
    async function login(silent = false) {
      const email = document.getElementById('authEmail').value;
      const password = document.getElementById('authPassword').value;
      const res = await apiCall('POST', '/api/v1/auth/login/', { email, password }, false);
      if (res.ok && res.data.access) {
        authToken = res.data.access;
        localStorage.setItem('cms_jwt_token', authToken);
        document.getElementById('tokenDisplay').textContent = authToken;
        document.getElementById('headerUserEmail').textContent = email;
        await loadWorkspaces();
      } else if (!silent) {
        alert('Login failed: ' + JSON.stringify(res.data));
      }
    }

    async function fetchMe() {
      const res = await apiCall('GET', '/api/v1/auth/me/');
      if (res.ok) {
        document.getElementById('headerUserEmail').textContent = res.data.email || 'User';
      }
    }

    function logout() {
      authToken = '';
      localStorage.removeItem('cms_jwt_token');
      document.getElementById('tokenDisplay').textContent = 'Logged out.';
      document.getElementById('headerUserEmail').textContent = 'Not Logged In';
    }

    function copyToken() {
      if (!authToken) { alert('No active token to copy.'); return; }
      navigator.clipboard.writeText(authToken);
      alert('JWT Access Token copied to clipboard!');
    }

    // Tenancy Operations
    async function loadWorkspaces() {
      const res = await apiCall('GET', '/api/v1/workspaces/');
      const select = document.getElementById('workspaceSelect');
      select.innerHTML = '';
      const items = Array.isArray(res.data) ? res.data : (res.data && res.data.results ? res.data.results : []);
      if (res.ok && items.length > 0) {
        currentWorkspaces = items;
        items.forEach(w => {
          const opt = document.createElement('option');
          opt.value = w.id;
          opt.textContent = `${w.name} (${w.slug})`;
          select.appendChild(opt);
        });
        loadSites();
      }
    }

    async function loadSites() {
      const wId = document.getElementById('workspaceSelect').value;
      if (!wId) return;
      const res = await apiCall('GET', `/api/v1/workspaces/${wId}/sites/`);
      const select = document.getElementById('siteSelect');
      select.innerHTML = '';
      const items = Array.isArray(res.data) ? res.data : (res.data && res.data.results ? res.data.results : []);
      if (res.ok && items.length > 0) {
        currentSites = items;
        items.forEach(s => {
          const opt = document.createElement('option');
          opt.value = s.id;
          opt.dataset.slug = s.slug;
          opt.textContent = `${s.name} (${s.slug})`;
          select.appendChild(opt);
        });
        loadArticles();
      }
    }

    async function createSite() {
      const wId = document.getElementById('workspaceSelect').value;
      const name = document.getElementById('newSiteName').value;
      const slug = document.getElementById('newSiteSlug').value;
      const locale = document.getElementById('newSiteLocale').value;
      const res = await apiCall('POST', `/api/v1/workspaces/${wId}/sites/`, { name, slug, default_locale: locale });
      if (res.ok) {
        alert('Site created successfully!');
        loadSites();
      }
    }

    // Content Operations
    async function createArticle() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      const title = document.getElementById('artTitle').value;
      const slug = document.getElementById('artSlug').value;
      const body = document.getElementById('artBody').value;

      const res = await apiCall('POST', `/api/v1/workspaces/${wId}/sites/${sId}/articles/`, {
        title, slug, body, status: 'DRAFT'
      });
      if (res.ok) {
        alert('Article created in DRAFT state!');
        loadArticles();
      }
    }

    async function loadArticles() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      const res = await apiCall('GET', `/api/v1/workspaces/${wId}/sites/${sId}/articles/`);
      const tbody = document.getElementById('articlesTableBody');
      tbody.innerHTML = '';
      document.getElementById('articlesTableCard')?.scrollIntoView({ behavior: 'smooth' });

      const items = Array.isArray(res.data) ? res.data : (res.data && res.data.results ? res.data.results : []);
      if (res.ok) {
        if (items.length === 0) {
          tbody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-dim)">No articles found in this site.</td></tr>';
          return;
        }
        items.forEach(art => {
          const isPublished = art.status === 'PUBLISHED';
          const badgeStyle = isPublished
            ? 'background:rgba(16,185,129,0.15); color:#10b981; border:1px solid rgba(16,185,129,0.3);'
            : 'background:rgba(245,158,11,0.15); color:#f59e0b; border:1px solid rgba(245,158,11,0.3);';
          const badgeText = isPublished ? '🟢 LIVE PUBLISHED' : '🟡 DRAFT (Private)';
          const actionBtn = isPublished
            ? `<button class="btn btn-secondary" style="font-size:0.75rem; padding:0.28rem 0.65rem;" onclick="publishArticle('${art.id}')">Re-Publish</button>`
            : `<button class="btn btn-success" style="font-size:0.75rem; padding:0.28rem 0.75rem; font-weight:700;" onclick="publishArticle('${art.id}')">🚀 Publish to Site</button>`;

          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td><strong>${art.title}</strong></td>
            <td><code>${art.slug}</code></td>
            <td><span style="${badgeStyle} padding:3px 8px; border-radius:4px; font-weight:600; font-size:0.75rem;">${badgeText}</span></td>
            <td>${actionBtn}</td>
          `;
          tbody.appendChild(tr);
        });
      }
    }

    async function publishArticle(artId) {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      const res = await apiCall('POST', `/api/v1/workspaces/${wId}/sites/${sId}/articles/${artId}/publish/`);
      if (res.ok) {
        alert('Article published! Live snapshot created and instantly viewable on public frontend.');
        loadArticles();
      }
    }

    async function viewPublicDelivery() {
      const sOpt = document.getElementById('siteSelect').selectedOptions[0];
      const slug = (sOpt && sOpt.dataset.slug) ? sOpt.dataset.slug : 'techradar-demo';
      await apiCall('GET', `/api/v1/public/sites/${slug}/articles/`, null, false);
    }

    // SEO Previews & Integrations
    async function previewSitemap() {
      const sOpt = document.getElementById('siteSelect').selectedOptions[0];
      const slug = (sOpt && sOpt.dataset.slug) ? sOpt.dataset.slug : 'techradar-demo';
      const res = await apiCall('GET', `/api/v1/public/sites/${slug}/sitemap.xml`, null, false);
      document.getElementById('seoPreviewDisplay').textContent = typeof res.data === 'string' ? res.data : JSON.stringify(res.data, null, 2);
    }

    async function previewRobots() {
      const sOpt = document.getElementById('siteSelect').selectedOptions[0];
      const slug = (sOpt && sOpt.dataset.slug) ? sOpt.dataset.slug : 'techradar-demo';
      const res = await apiCall('GET', `/api/v1/public/sites/${slug}/robots.txt`, null, false);
      document.getElementById('seoPreviewDisplay').textContent = typeof res.data === 'string' ? res.data : JSON.stringify(res.data, null, 2);
    }

    async function checkSearchProviders() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      await apiCall('GET', `/api/v1/workspaces/${wId}/sites/${sId}/integrations/connections/`);
    }

    async function inspectIndexNowKey() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      await apiCall('GET', `/api/v1/workspaces/${wId}/sites/${sId}/integrations/indexnow/`);
    }

    async function viewIndexingLogs() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      await apiCall('GET', `/api/v1/workspaces/${wId}/sites/${sId}/integrations/logs/`);
    }

    async function submitUrlForIndexing() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      const provider = document.getElementById('indexingProvider').value;
      const url = document.getElementById('indexingUrl').value;
      await apiCall('POST', `/api/v1/workspaces/${wId}/sites/${sId}/integrations/submit/`, {
        provider,
        urls: [url]
      });
    }

    // Analytics Ingestion, Overview & GA4
    async function ingestEvent(eventType, path) {
      const sOpt = document.getElementById('siteSelect').selectedOptions[0];
      const slug = (sOpt && sOpt.dataset.slug) ? sOpt.dataset.slug : 'techradar-demo';
      const visitorId = 'vis-' + Math.random().toString(36).substring(2, 10);
      const sessionId = 'ses-' + Math.random().toString(36).substring(2, 10);

      let properties = {};
      if (eventType === 'page_view') {
        properties = { path: path, referrer: 'https://techradar.io', title: 'TechRadar Demo' };
      } else if (eventType === 'cta_click') {
        properties = { path: path, cta_id: 'cta-primary', cta_text: 'Get Started', target_url: 'https://techradar.io/pricing' };
      } else if (eventType === 'form_submit') {
        properties = { path: path, form_id: 'form-contact-01', form_name: 'Lead Contact Form' };
      }

      await apiCall('POST', `/api/v1/public/sites/${slug}/events`, {
        event_type: eventType,
        visitor_id: visitorId,
        session_id: sessionId,
        path: path,
        consent_granted: true,
        properties: properties
      }, false);
    }

    async function loadAnalyticsMetrics() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      const res = await apiCall('GET', `/api/v1/workspaces/${wId}/sites/${sId}/analytics/first-party/overview/`);
      if (res.ok && res.data.summary) {
        document.getElementById('statEvents').textContent = res.data.summary.total_events || 0;
        document.getElementById('statVisitors').textContent = res.data.summary.unique_visitors || 0;
        document.getElementById('statViews').textContent = res.data.summary.page_views || 0;
        document.getElementById('statClicks').textContent = res.data.summary.cta_clicks || 0;
      }
    }

    async function checkAnalyticsConfig() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      await apiCall('GET', `/api/v1/workspaces/${wId}/sites/${sId}/analytics/config/`);
    }

    async function connectGA4Mock() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      await apiCall('POST', `/api/v1/workspaces/${wId}/sites/${sId}/analytics/ga4/`, {
        property_id: '123456789',
        measurement_id: 'G-DEMOTEST12',
        credentials: { client_id: 'demo-client', client_secret: 'demo-secret' }
      });
    }

    async function fetchGA4Report() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      const now = new Date();
      const today = now.toISOString().split('T')[0];
      const past = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
      await apiCall('GET', `/api/v1/workspaces/${wId}/sites/${sId}/analytics/reports/ga4/?start_date=${past}&end_date=${today}`);
    }

    // Consent Operations
    async function recordConsent(analyticsChoice, marketingChoice) {
      const sOpt = document.getElementById('siteSelect').selectedOptions[0];
      const slug = (sOpt && sOpt.dataset.slug) ? sOpt.dataset.slug : 'techradar-demo';
      const visitorId = document.getElementById('consentVisitorId').value || 'vis-test-101';

      await apiCall('POST', `/api/v1/public/sites/${slug}/consent`, {
        visitor_id: visitorId,
        categories: {
          analytics: analyticsChoice,
          marketing: marketingChoice
        },
        consent_type: (analyticsChoice && marketingChoice) ? 'EXPLICIT_OPT_IN' : 'OPT_OUT'
      }, false);
    }

    // GitHub Operations & Automation
    async function fetchInstallations() {
      const wId = document.getElementById('workspaceSelect').value;
      const res = await apiCall('GET', `/api/v1/workspaces/${wId}/github/installations/`);
      if (res.ok && Array.isArray(res.data) && res.data.length > 0) {
        document.getElementById('ghInstallationId').value = res.data[0].installation_id;
      }
    }

    async function fetchAccessibleRepos() {
      const wId = document.getElementById('workspaceSelect').value;
      const instId = document.getElementById('ghInstallationId').value;
      if (!instId) { alert('Enter an Installation ID'); return; }
      const res = await apiCall('GET', `/api/v1/workspaces/${wId}/github/installations/${instId}/repositories/`);
      const container = document.getElementById('repoListDisplay');
      if (res.ok && res.data && res.data.repositories) {
        let html = '<div class="table-container"><table><thead><tr><th>Repository</th><th>Default Branch</th><th>Visibility</th><th>Action</th></tr></thead><tbody>';
        res.data.repositories.forEach(r => {
          const repoName = r.full_name || r.name;
          html += `<tr>
            <td><strong>${repoName}</strong></td>
            <td><code>${r.default_branch || 'main'}</code></td>
            <td><span class="inspector-badge">${r.private ? 'PRIVATE' : 'PUBLIC'}</span></td>
            <td><button class="btn btn-secondary" style="font-size:0.75rem; padding:0.25rem 0.5rem" onclick="selectRepo('${repoName}')">Select</button></td>
          </tr>`;
        });
        html += '</tbody></table></div>';
        container.innerHTML = html;
      }
    }

    function selectRepo(name) {
      document.getElementById('ghRepoFullName').value = name;
      alert('Selected repository: ' + name);
    }

    async function connectRepoToSite() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      const repoFullName = document.getElementById('ghRepoFullName').value;
      const baseBranch = document.getElementById('ghBaseBranch').value;
      const instId = parseInt(document.getElementById('ghInstallationId').value, 10);
      await apiCall('POST', `/api/v1/workspaces/${wId}/sites/${sId}/github/connect/`, {
        installation_id: instId,
        repo_full_name: repoFullName,
        base_branch: baseBranch
      });
    }

    async function analyzeConnectedRepo() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      await apiCall('POST', `/api/v1/workspaces/${wId}/sites/${sId}/github/analyze/`);
    }

    async function openIntegrationPR() {
      const wId = document.getElementById('workspaceSelect').value;
      const sId = document.getElementById('siteSelect').value;
      await apiCall('POST', `/api/v1/workspaces/${wId}/sites/${sId}/github/open-pr/`);
    }

    // Establish session on load: reuse stored token, otherwise auto-login with the prefilled demo credentials
    let sessionReady;
    if (authToken) {
      document.getElementById('tokenDisplay').textContent = authToken;
      sessionReady = fetchMe().then(() => loadWorkspaces());
    } else {
      sessionReady = login(true);
    }

    // Auto-detect GitHub App Installation callback from query params
    const urlParams = new URLSearchParams(window.location.search);
    const instParam = urlParams.get('installation_id');
    if (instParam) {
      const input = document.getElementById('ghInstallationId');
      if (input) input.value = instParam;
      if (urlParams.get('installed')) {
        sessionReady.then(() => {
          document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
          document.querySelectorAll('.nav-btn').forEach(el => el.classList.remove('active'));
          document.getElementById('tab-github')?.classList.add('active');
          alert('GitHub App successfully installed! Installation ID ' + instParam + ' registered.');
          fetchAccessibleRepos();
        });
      }
    }
  </script>
</body>
</html>
"""


def testing_console_view(request: HttpRequest) -> HttpResponse:
    """Serve the interactive developer and QA testing console."""
    return HttpResponse(CONSOLE_HTML, content_type="text/html")
