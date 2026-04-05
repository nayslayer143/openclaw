# Phase 7: Landing Page + Interactive Demo

> Part of iFauxto v2 plan. Read `2026-04-04-ifauxto-v2-plan.md` first. This phase is independent of Phases 1-6 and can run in parallel.

**Goal:** Marketing landing page with a fully interactive browser-based demo of iFauxto. Guided tooltip walkthrough teaches users the killer features.

**Location:** `~/openclaw/builds/ifauxto/landing/`
**Tech:** HTML, CSS, vanilla JS (no framework — keeps it fast and simple)
**Deploy:** Static files — Vercel, Netlify, or GitHub Pages

---

### Task 1: Scaffold landing page structure

**Files:**
- Create: `landing/index.html`
- Create: `landing/src/styles.css`

- [ ] **Step 1: Create directory structure**

```bash
cd ~/openclaw/builds/ifauxto && mkdir -p landing/src landing/assets/photos landing/assets/mockup landing/assets/icons
```

- [ ] **Step 2: Create index.html**

Create `landing/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iFauxto — Your photos. Your order.</title>
    <link rel="stylesheet" href="src/styles.css">
</head>
<body>
    <!-- Hero -->
    <section class="hero" id="hero">
        <div class="hero-content">
            <h1>Your photos.<br>Your order.</h1>
            <p class="subtitle">Apple decides what you see. We think that's your job.</p>
            <a href="#demo" class="cta-button">Try the Demo</a>
        </div>
    </section>

    <!-- Features -->
    <section class="features" id="features">
        <div class="feature">
            <div class="feature-icon">📌</div>
            <h2>Folders that stay put</h2>
            <p>Drag once. Done forever. No reshuffling. No "helpful" reordering. Your muscle memory works here.</p>
        </div>
        <div class="feature">
            <div class="feature-icon">🔍</div>
            <h2>Find anything. Instantly.</h2>
            <p>Every photo tagged automatically on your device. Search "beach" or "night" and get results in milliseconds. Free. Private.</p>
        </div>
        <div class="feature">
            <div class="feature-icon">🎨</div>
            <h2>Edit your way</h2>
            <p>VSCO-quality sliders. Non-destructive. Your original is always safe.</p>
        </div>
        <div class="feature">
            <div class="feature-icon">🏠</div>
            <h2>Your app, your entry</h2>
            <p>Choose what you see when you open the app. Folders? Feed? Last opened? You decide.</p>
        </div>
    </section>

    <!-- Interactive Demo -->
    <section class="demo-section" id="demo">
        <h2>Try it yourself</h2>
        <p class="demo-subtitle">This is a live, interactive demo. Click around. Drag folders. Search photos.</p>
        <div class="phone-frame">
            <div class="demo-app" id="demo-app">
                <!-- Demo content injected by JS -->
            </div>
        </div>
    </section>

    <!-- CTA -->
    <section class="cta-section" id="cta">
        <h2>Ready to take control?</h2>
        <p>No surprises. Just your system.</p>
        <a href="#" class="cta-button cta-large">Download on the App Store</a>
        <p class="cta-note">Or <a href="#" class="waitlist-link">join the waitlist</a> for early access.</p>
    </section>

    <footer>
        <p>iFauxto — Finally, your photos behave.</p>
    </footer>

    <script src="src/data.js"></script>
    <script src="src/demo.js"></script>
    <script src="src/tooltips.js"></script>
</body>
</html>
```

- [ ] **Step 3: Create styles.css**

Create `landing/src/styles.css`:

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --bg: #0a0a0a;
    --text: #f5f5f5;
    --accent: #3b82f6;
    --muted: #888;
    --card: #1a1a1a;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
}

/* Hero */
.hero {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    padding: 2rem;
}

.hero h1 {
    font-size: clamp(2.5rem, 8vw, 5rem);
    font-weight: 800;
    letter-spacing: -0.03em;
    line-height: 1.1;
}

.subtitle {
    font-size: 1.25rem;
    color: var(--muted);
    margin-top: 1rem;
    max-width: 500px;
    margin-left: auto;
    margin-right: auto;
}

.cta-button {
    display: inline-block;
    margin-top: 2rem;
    padding: 0.875rem 2rem;
    background: var(--accent);
    color: white;
    border-radius: 12px;
    text-decoration: none;
    font-weight: 600;
    font-size: 1.1rem;
    transition: transform 0.2s, box-shadow 0.2s;
}

.cta-button:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(59, 130, 246, 0.3);
}

/* Features */
.features {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 2rem;
    max-width: 1000px;
    margin: 0 auto;
    padding: 4rem 2rem;
}

.feature {
    background: var(--card);
    border-radius: 16px;
    padding: 2rem;
}

.feature-icon {
    font-size: 2rem;
    margin-bottom: 1rem;
}

.feature h2 {
    font-size: 1.25rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
}

.feature p {
    color: var(--muted);
    font-size: 0.95rem;
}

/* Demo Section */
.demo-section {
    text-align: center;
    padding: 4rem 2rem;
}

.demo-section h2 {
    font-size: 2rem;
    font-weight: 700;
}

.demo-subtitle {
    color: var(--muted);
    margin-top: 0.5rem;
    margin-bottom: 2rem;
}

.phone-frame {
    width: 375px;
    height: 812px;
    margin: 0 auto;
    border: 3px solid #333;
    border-radius: 40px;
    overflow: hidden;
    background: white;
    position: relative;
}

.demo-app {
    width: 100%;
    height: 100%;
    overflow-y: auto;
    font-family: -apple-system, sans-serif;
    color: #000;
    background: #f2f2f7;
}

/* Demo internal styles */
.demo-nav { padding: 60px 16px 12px; background: #f2f2f7; }
.demo-nav h1 { font-size: 28px; font-weight: 700; }
.demo-folder-list { padding: 0 16px; }
.demo-folder {
    display: flex; align-items: center; gap: 12px;
    padding: 14px 0; border-bottom: 1px solid #e5e5ea;
    cursor: grab; user-select: none;
    transition: background 0.15s;
}
.demo-folder:active { background: #e5e5ea; }
.demo-folder-icon { font-size: 24px; }
.demo-folder-name { font-size: 17px; font-weight: 500; }
.demo-folder-count { font-size: 13px; color: #8e8e93; }
.demo-search {
    margin: 8px 16px; padding: 10px 12px;
    background: #e5e5ea; border-radius: 10px;
    border: none; width: calc(100% - 32px);
    font-size: 16px; outline: none;
}
.demo-photo-grid {
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 2px; padding: 2px;
}
.demo-photo {
    aspect-ratio: 1; background-size: cover;
    background-position: center; border-radius: 2px;
    cursor: pointer;
}

/* Tooltip */
.tooltip {
    position: absolute;
    background: var(--accent);
    color: white;
    padding: 12px 16px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 500;
    max-width: 260px;
    z-index: 100;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    animation: tooltipFade 0.3s ease;
}

.tooltip::after {
    content: '';
    position: absolute;
    width: 12px; height: 12px;
    background: var(--accent);
    transform: rotate(45deg);
}

.tooltip-bottom::after { top: -6px; left: 50%; margin-left: -6px; }
.tooltip-top::after { bottom: -6px; left: 50%; margin-left: -6px; }

.tooltip .skip-btn {
    display: block; margin-top: 8px;
    font-size: 12px; opacity: 0.7;
    cursor: pointer; text-decoration: underline;
}

@keyframes tooltipFade {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

/* CTA Section */
.cta-section {
    text-align: center;
    padding: 6rem 2rem;
}

.cta-section h2 { font-size: 2.5rem; font-weight: 800; }
.cta-section p { color: var(--muted); margin-top: 0.5rem; }
.cta-large { margin-top: 2rem; font-size: 1.2rem; padding: 1rem 2.5rem; }
.cta-note { margin-top: 1rem; font-size: 0.9rem; color: var(--muted); }
.waitlist-link { color: var(--accent); }

footer {
    text-align: center;
    padding: 2rem;
    color: var(--muted);
    font-size: 0.85rem;
}

/* Pulse animation for final CTA */
@keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
    50% { box-shadow: 0 0 0 12px rgba(59, 130, 246, 0); }
}
.cta-pulse { animation: pulse 2s infinite; }
```

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add landing/ && git commit -m "feat: scaffold landing page with hero, features, demo frame, CTA sections"
```

---

### Task 2: Create demo data and interactive demo engine

**Files:**
- Create: `landing/src/data.js`
- Create: `landing/src/demo.js`

- [ ] **Step 1: Create data.js with sample folders and photos**

Create `landing/src/data.js`:

```javascript
const DEMO_DATA = {
    folders: [
        { id: 'trips', name: 'Trips', count: 8, color: '#fbbf24' },
        { id: 'family', name: 'Family', count: 12, color: '#fbbf24' },
        { id: 'screenshots', name: 'Screenshots', count: 6, color: '#fbbf24' },
        { id: 'food', name: 'Food', count: 7, color: '#fbbf24' },
        { id: 'architecture', name: 'Architecture', count: 5, color: '#fbbf24' },
    ],
    photos: {
        trips: [
            { id: 't1', tags: ['beach', 'ocean', 'sunset', 'evening'], color: '#3b82f6' },
            { id: 't2', tags: ['mountain', 'snow', 'morning'], color: '#6366f1' },
            { id: 't3', tags: ['city', 'night', 'lights'], color: '#1e1b4b' },
            { id: 't4', tags: ['forest', 'trail', 'morning'], color: '#166534' },
            { id: 't5', tags: ['beach', 'palm', 'afternoon'], color: '#0891b2' },
            { id: 't6', tags: ['airport', 'travel', 'morning'], color: '#78716c' },
            { id: 't7', tags: ['lake', 'reflection', 'evening'], color: '#1d4ed8' },
            { id: 't8', tags: ['desert', 'sand', 'afternoon'], color: '#d97706' },
        ],
        family: [
            { id: 'f1', tags: ['people', 'portrait', '2 faces', 'afternoon'], color: '#f472b6' },
            { id: 'f2', tags: ['people', 'group', '4 faces', 'evening'], color: '#e879f9' },
            { id: 'f3', tags: ['people', 'child', '1 face', 'morning'], color: '#fb923c' },
            { id: 'f4', tags: ['people', 'outdoor', '3 faces', 'afternoon'], color: '#a3e635' },
            { id: 'f5', tags: ['people', 'celebration', '5 faces', 'night'], color: '#f43f5e' },
            { id: 'f6', tags: ['people', 'portrait', '1 face', 'morning'], color: '#c084fc' },
            { id: 'f7', tags: ['people', 'park', '2 faces', 'afternoon'], color: '#34d399' },
            { id: 'f8', tags: ['people', 'dinner', '3 faces', 'evening'], color: '#fbbf24' },
            { id: 'f9', tags: ['people', 'beach', '2 faces', 'afternoon'], color: '#38bdf8' },
            { id: 'f10', tags: ['people', 'holiday', '4 faces', 'morning'], color: '#fb7185' },
            { id: 'f11', tags: ['people', 'selfie', '2 faces', 'night'], color: '#a78bfa' },
            { id: 'f12', tags: ['people', 'garden', '1 face', 'afternoon'], color: '#4ade80' },
        ],
        screenshots: [
            { id: 's1', tags: ['screenshot', 'text', 'morning'], color: '#e2e8f0' },
            { id: 's2', tags: ['screenshot', 'text', 'afternoon'], color: '#cbd5e1' },
            { id: 's3', tags: ['screenshot', 'text', 'night'], color: '#94a3b8' },
            { id: 's4', tags: ['screenshot', 'text', 'morning'], color: '#f1f5f9' },
            { id: 's5', tags: ['screenshot', 'text', 'evening'], color: '#e2e8f0' },
            { id: 's6', tags: ['screenshot', 'text', 'afternoon'], color: '#cbd5e1' },
        ],
        food: [
            { id: 'fo1', tags: ['food', 'restaurant', 'dinner', 'evening'], color: '#dc2626' },
            { id: 'fo2', tags: ['food', 'coffee', 'cafe', 'morning'], color: '#92400e' },
            { id: 'fo3', tags: ['food', 'sushi', 'dinner', 'night'], color: '#f97316' },
            { id: 'fo4', tags: ['food', 'dessert', 'cake', 'afternoon'], color: '#ec4899' },
            { id: 'fo5', tags: ['food', 'brunch', 'morning'], color: '#eab308' },
            { id: 'fo6', tags: ['food', 'street', 'afternoon'], color: '#ef4444' },
            { id: 'fo7', tags: ['food', 'homemade', 'evening'], color: '#b45309' },
        ],
        architecture: [
            { id: 'a1', tags: ['building', 'modern', 'glass', 'afternoon'], color: '#64748b' },
            { id: 'a2', tags: ['building', 'historic', 'stone', 'morning'], color: '#a8a29e' },
            { id: 'a3', tags: ['bridge', 'night', 'lights'], color: '#334155' },
            { id: 'a4', tags: ['interior', 'design', 'afternoon'], color: '#d6d3d1' },
            { id: 'a5', tags: ['building', 'skyline', 'evening'], color: '#475569' },
        ],
    },
    allTags: ['beach', 'ocean', 'sunset', 'mountain', 'city', 'night', 'food', 'people', 'screenshot', 'morning', 'evening', 'afternoon', 'building', 'forest', 'coffee', 'portrait'],
};
```

- [ ] **Step 2: Create demo.js with interactive folder list and search**

Create `landing/src/demo.js`:

```javascript
(function() {
    const app = document.getElementById('demo-app');
    let currentView = 'home';
    let folderOrder = [...DEMO_DATA.folders];

    function render() {
        if (currentView === 'home') renderHome();
        else if (currentView.startsWith('folder:')) renderFolder(currentView.split(':')[1]);
        else if (currentView === 'search') renderSearch();
    }

    function renderHome() {
        app.innerHTML = `
            <div class="demo-nav"><h1>iFauxto</h1></div>
            <input class="demo-search" placeholder="Find anything. Instantly." id="demo-search-input">
            <div class="demo-folder-list" id="folder-list">
                ${folderOrder.map(f => `
                    <div class="demo-folder" draggable="true" data-id="${f.id}">
                        <span class="demo-folder-icon">📁</span>
                        <div>
                            <div class="demo-folder-name">${f.name}</div>
                            <div class="demo-folder-count">${f.count} photos</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
        setupFolderDrag();
        document.getElementById('demo-search-input').addEventListener('focus', () => {
            currentView = 'search';
            render();
        });
        document.querySelectorAll('.demo-folder').forEach(el => {
            el.addEventListener('click', (e) => {
                if (e.target.closest('[draggable]') && !e.defaultPrevented) {
                    currentView = 'folder:' + el.dataset.id;
                    render();
                }
            });
        });
    }

    function renderFolder(folderId) {
        const folder = DEMO_DATA.folders.find(f => f.id === folderId);
        const photos = DEMO_DATA.photos[folderId] || [];
        app.innerHTML = `
            <div class="demo-nav">
                <span style="cursor:pointer;font-size:16px;color:#007aff;" id="back-btn">← Back</span>
                <h1 style="font-size:22px;margin-top:8px;">${folder.name}</h1>
            </div>
            <div class="demo-photo-grid">
                ${photos.map(p => `
                    <div class="demo-photo" style="background-color:${p.color};" data-tags="${p.tags.join(',')}"></div>
                `).join('')}
            </div>
        `;
        document.getElementById('back-btn').addEventListener('click', () => {
            currentView = 'home';
            render();
        });
    }

    function renderSearch() {
        app.innerHTML = `
            <div class="demo-nav">
                <span style="cursor:pointer;font-size:16px;color:#007aff;" id="search-back">Cancel</span>
                <input class="demo-search" placeholder="Search photos..." id="search-input" autofocus>
            </div>
            <div id="search-results" style="padding:8px;"></div>
            <div id="search-suggestions" style="padding:0 16px;"></div>
        `;
        document.getElementById('search-back').addEventListener('click', () => {
            currentView = 'home';
            render();
        });
        const input = document.getElementById('search-input');
        input.addEventListener('input', () => {
            const q = input.value.toLowerCase().trim();
            if (!q) {
                document.getElementById('search-results').innerHTML = '';
                showSuggestions();
                return;
            }
            const matches = [];
            Object.values(DEMO_DATA.photos).flat().forEach(p => {
                if (p.tags.some(t => t.includes(q))) matches.push(p);
            });
            document.getElementById('search-results').innerHTML = matches.length
                ? `<div class="demo-photo-grid">${matches.map(p =>
                    `<div class="demo-photo" style="background-color:${p.color};"></div>`
                ).join('')}</div>`
                : `<p style="text-align:center;color:#8e8e93;padding:40px;">No results for "${input.value}"</p>`;
        });
        showSuggestions();
    }

    function showSuggestions() {
        const el = document.getElementById('search-suggestions');
        if (!el) return;
        el.innerHTML = DEMO_DATA.allTags.slice(0, 8).map(t =>
            `<span style="display:inline-block;padding:6px 12px;margin:4px;background:#e5e5ea;border-radius:16px;font-size:14px;cursor:pointer;" class="tag-sug">${t}</span>`
        ).join('');
        el.querySelectorAll('.tag-sug').forEach(s => {
            s.addEventListener('click', () => {
                document.getElementById('search-input').value = s.textContent;
                document.getElementById('search-input').dispatchEvent(new Event('input'));
            });
        });
    }

    // Drag and drop for folders
    let draggedId = null;
    function setupFolderDrag() {
        const folders = document.querySelectorAll('.demo-folder');
        folders.forEach(el => {
            el.addEventListener('dragstart', (e) => {
                draggedId = el.dataset.id;
                el.style.opacity = '0.5';
                e.dataTransfer.effectAllowed = 'move';
            });
            el.addEventListener('dragend', () => {
                el.style.opacity = '1';
                draggedId = null;
            });
            el.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                el.style.background = '#e5e5ea';
            });
            el.addEventListener('dragleave', () => {
                el.style.background = '';
            });
            el.addEventListener('drop', (e) => {
                e.preventDefault();
                el.style.background = '';
                if (!draggedId || draggedId === el.dataset.id) return;
                const fromIdx = folderOrder.findIndex(f => f.id === draggedId);
                const toIdx = folderOrder.findIndex(f => f.id === el.dataset.id);
                const [moved] = folderOrder.splice(fromIdx, 1);
                folderOrder.splice(toIdx, 0, moved);
                render();
                // Dispatch event for tooltip system
                window.dispatchEvent(new CustomEvent('demo:folderReordered'));
            });
        });
    }

    // Init
    render();
    window.demoRender = render;
    window.demoNavigate = (view) => { currentView = view; render(); };
})();
```

- [ ] **Step 3: Verify locally**

```bash
cd ~/openclaw/builds/ifauxto/landing && python3 -m http.server 8080 &
echo "Open http://localhost:8080 in browser to verify"
```

- [ ] **Step 4: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add landing/src/data.js landing/src/demo.js && git commit -m "feat: add interactive demo engine with drag-and-drop folders and live search"
```

---

### Task 3: Create guided tooltip walkthrough

**Files:**
- Create: `landing/src/tooltips.js`

- [ ] **Step 1: Create tooltips.js**

Create `landing/src/tooltips.js`:

```javascript
(function() {
    const STEPS = [
        {
            target: '.demo-nav h1',
            text: 'Welcome to iFauxto. This is YOUR photo library.',
            position: 'bottom',
            auto: true,
            delay: 1000,
        },
        {
            target: '.demo-folder',
            text: 'Try dragging a folder. Go ahead — it stays where you put it.',
            position: 'bottom',
            waitFor: 'demo:folderReordered',
            completionText: 'See? No reshuffling. Ever.',
        },
        {
            target: '.demo-search',
            text: 'Now try searching. Type "beach" or "night".',
            position: 'bottom',
            waitFor: 'input',
            waitTarget: '#demo-search-input',
            completionText: 'Every photo tagged automatically. On your device. Free.',
        },
        {
            target: '.demo-photo',
            text: 'Each photo is tagged with objects, scenes, faces, and text — all on-device.',
            position: 'top',
            auto: true,
            delay: 3000,
        },
        {
            target: '#cta',
            text: 'Ready to take control?',
            position: 'top',
            auto: true,
            final: true,
        },
    ];

    let currentStep = 0;
    let tooltipEl = null;

    // Check localStorage — don't re-show
    if (localStorage.getItem('ifauxto-walkthrough-done')) return;

    function showStep(index) {
        removeTooltip();
        if (index >= STEPS.length) {
            localStorage.setItem('ifauxto-walkthrough-done', 'true');
            return;
        }

        const step = STEPS[index];
        const target = document.querySelector(step.target);
        if (!target) {
            // Target not visible, try again after render
            setTimeout(() => showStep(index), 500);
            return;
        }

        // Scroll target into view
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });

        setTimeout(() => {
            tooltipEl = document.createElement('div');
            tooltipEl.className = `tooltip tooltip-${step.position}`;
            tooltipEl.innerHTML = `
                ${step.text}
                <span class="skip-btn" id="tooltip-skip">Skip walkthrough</span>
            `;

            const rect = target.getBoundingClientRect();
            if (step.position === 'bottom') {
                tooltipEl.style.top = (rect.bottom + window.scrollY + 12) + 'px';
                tooltipEl.style.left = (rect.left + rect.width / 2 - 130) + 'px';
            } else {
                tooltipEl.style.top = (rect.top + window.scrollY - 60) + 'px';
                tooltipEl.style.left = (rect.left + rect.width / 2 - 130) + 'px';
            }

            document.body.appendChild(tooltipEl);

            document.getElementById('tooltip-skip').addEventListener('click', () => {
                removeTooltip();
                localStorage.setItem('ifauxto-walkthrough-done', 'true');
            });

            if (step.auto) {
                setTimeout(() => {
                    if (step.completionText) showCompletion(step.completionText);
                    else advance();
                }, step.delay || 2000);
            } else if (step.waitFor === 'demo:folderReordered') {
                window.addEventListener('demo:folderReordered', function handler() {
                    window.removeEventListener('demo:folderReordered', handler);
                    showCompletion(step.completionText);
                });
            } else if (step.waitFor === 'input' && step.waitTarget) {
                const check = setInterval(() => {
                    const el = document.querySelector(step.waitTarget);
                    if (el && el.value.length >= 3) {
                        clearInterval(check);
                        setTimeout(() => showCompletion(step.completionText), 500);
                    }
                }, 300);
            }

            if (step.final) {
                const cta = document.querySelector('.cta-large');
                if (cta) cta.classList.add('cta-pulse');
            }
        }, 300);
    }

    function showCompletion(text) {
        if (tooltipEl) tooltipEl.innerHTML = `${text}<br><span class="skip-btn" onclick="window.__advanceTooltip()">Next →</span>`;
    }

    function advance() {
        currentStep++;
        showStep(currentStep);
    }

    window.__advanceTooltip = advance;

    function removeTooltip() {
        if (tooltipEl) {
            tooltipEl.remove();
            tooltipEl = null;
        }
    }

    // Start walkthrough when demo section is in view
    const observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) {
            observer.disconnect();
            setTimeout(() => showStep(0), 500);
        }
    });
    const demoSection = document.getElementById('demo');
    if (demoSection) observer.observe(demoSection);
})();
```

- [ ] **Step 2: Test locally**

```bash
# Clear localStorage in browser (or use incognito) and reload http://localhost:8080
# Verify: tooltip appears when scrolling to demo, guides through drag/search steps
```

- [ ] **Step 3: Commit**

```bash
cd ~/openclaw/builds/ifauxto && git add landing/src/tooltips.js && git commit -m "feat: add guided tooltip walkthrough with 5-step interactive tutorial"
```

---

## Phase 7 Complete

After all 3 tasks:
- Marketing landing page with hero, features, and CTA
- Fully interactive browser demo inside phone frame
- Drag-and-drop folders, live search, photo grid all working
- 5-step guided walkthrough with action-based triggers
- Static files — deploy anywhere (Vercel/Netlify/GitHub Pages)
- Walkthrough state persisted in localStorage (doesn't re-show)
