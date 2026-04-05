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
            target: '.cta-section',
            text: 'Ready to take control?',
            position: 'top',
            auto: true,
            final: true,
        },
    ];

    let currentStep = 0;
    let tooltipEl = null;

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
            setTimeout(() => showStep(index), 500);
            return;
        }

        target.scrollIntoView({ behavior: 'smooth', block: 'center' });

        setTimeout(() => {
            tooltipEl = document.createElement('div');
            tooltipEl.className = 'tooltip tooltip-' + step.position;
            tooltipEl.innerHTML = step.text +
                '<span class="skip-btn" id="tooltip-skip">Skip walkthrough</span>';

            const rect = target.getBoundingClientRect();
            if (step.position === 'bottom') {
                tooltipEl.style.top = (rect.bottom + window.scrollY + 12) + 'px';
                tooltipEl.style.left = Math.max(8, rect.left + rect.width / 2 - 130) + 'px';
            } else {
                tooltipEl.style.top = (rect.top + window.scrollY - 60) + 'px';
                tooltipEl.style.left = Math.max(8, rect.left + rect.width / 2 - 130) + 'px';
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
                const cta = document.querySelector('.cta-button');
                if (cta) cta.classList.add('cta-pulse');
            }
        }, 300);
    }

    function showCompletion(text) {
        if (tooltipEl) {
            tooltipEl.innerHTML = text +
                '<br><span class="skip-btn" onclick="window.__advanceTooltip()">Next &rarr;</span>';
        }
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

    const observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) {
            observer.disconnect();
            setTimeout(() => showStep(0), 500);
        }
    });
    const demoSection = document.getElementById('demo');
    if (demoSection) observer.observe(demoSection);
})();
