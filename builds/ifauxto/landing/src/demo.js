(function() {
    const app = document.getElementById('demo-app');
    if (!app) return;

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
        const searchInput = document.getElementById('demo-search-input');
        if (searchInput) {
            searchInput.addEventListener('focus', () => {
                currentView = 'search';
                render();
            });
        }
        document.querySelectorAll('.demo-folder').forEach(el => {
            el.addEventListener('click', () => {
                currentView = 'folder:' + el.dataset.id;
                render();
            });
        });
    }

    function renderFolder(folderId) {
        const folder = DEMO_DATA.folders.find(f => f.id === folderId);
        const photos = DEMO_DATA.photos[folderId] || [];
        app.innerHTML = `
            <div class="demo-nav">
                <span style="cursor:pointer;font-size:16px;color:#007aff;" id="back-btn">← Back</span>
                <h1 style="font-size:22px;margin-top:8px;">${folder ? folder.name : folderId}</h1>
            </div>
            <div class="demo-photo-grid">
                ${photos.map(p => `
                    <div class="demo-photo" style="background-color:${p.color};" title="${p.tags.join(', ')}"></div>
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
                    `<div class="demo-photo" style="background-color:${p.color};" title="${p.tags.join(', ')}"></div>`
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
                const input = document.getElementById('search-input');
                if (input) {
                    input.value = s.textContent;
                    input.dispatchEvent(new Event('input'));
                }
            });
        });
    }

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
                window.dispatchEvent(new CustomEvent('demo:folderReordered'));
            });
        });
    }

    render();
    window.demoRender = render;
    window.demoNavigate = (view) => { currentView = view; render(); };
})();
