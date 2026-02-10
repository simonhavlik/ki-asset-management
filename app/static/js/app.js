// Custom JavaScript for KI Asset Management

// Language configuration
window.LANG = {
    current: 'en',
    set: function(lang) {
        this.current = lang;
        document.documentElement.setAttribute('data-lang', lang);
        document.documentElement.setAttribute('lang', lang);
        // Update language indicator if exists
        var indicator = document.getElementById('lang-indicator');
        if (indicator) {
            indicator.textContent = lang.toUpperCase();
        }
    },
    detect: function() {
        var browserLang = navigator.language || navigator.userLanguage;
        return browserLang && browserLang.toLowerCase().startsWith('cs') ? 'cs' : 'en';
    },
    init: function() {
        var saved = localStorage.getItem('lang');
        var detected = saved || this.detect();
        this.set(detected);
    },
    toggle: function() {
        this.set(this.current === 'en' ? 'cs' : 'en');
        localStorage.setItem('lang', this.current);
        // Reload to apply translations
        window.location.reload();
    }
};

document.addEventListener('DOMContentLoaded', function() {
    // Initialize language
    window.LANG.init();
    
    // Enable Bootstrap tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Confirm before destructive actions
    const confirmButtons = document.querySelectorAll('[data-confirm]');
    confirmButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm') || 'Are you sure?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
    
    // Auto‑dismiss alerts after 5 seconds
    setTimeout(() => {
        const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(alert => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);
    
    // Initialize custom cursor on non-touch devices
    initCustomCursor();
});

// Custom Inverted Cursor with Color Inversion Sphere
function initCustomCursor() {
    // Only on non-touch devices
    if (window.matchMedia('(pointer: coarse)').matches) return;
    
    // Check if cursor already exists
    if (document.querySelector('.custom-cursor')) return;
    
    const cursor = document.createElement('div');
    cursor.className = 'custom-cursor';
    document.body.appendChild(cursor);
    
    const cursorDot = document.createElement('div');
    cursorDot.className = 'cursor-dot';
    document.body.appendChild(cursorDot);
    
    let mouseX = 0, mouseY = 0;
    let cursorX = 0, cursorY = 0;
    let rafId = null;
    let isActive = true;
    let mouseTimeout = null;
    
    function updateCursor() {
        if (!isActive) return;
        
        // Smooth follow with lerp
        cursorX += (mouseX - cursorX) * 0.12;
        cursorY += (mouseY - cursorY) * 0.12;
        
        cursor.style.left = cursorX + 'px';
        cursor.style.top = cursorY + 'px';
        
        rafId = requestAnimationFrame(updateCursor);
    }
    
    document.addEventListener('mousemove', (e) => {
        mouseX = e.clientX;
        mouseY = e.clientY;
        
        cursorDot.style.left = mouseX + 'px';
        cursorDot.style.top = mouseY + 'px';
        
        // Add active class to show inversion sphere
        cursor.classList.add('active');
        
        // Clear existing timeout
        if (mouseTimeout) clearTimeout(mouseTimeout);
        
        // Set timeout to hide inversion sphere after mouse stops
        mouseTimeout = setTimeout(() => {
            cursor.classList.remove('active');
        }, 100);
    }, { passive: true });
    
    // Start animation
    updateCursor();
    
    // Hover effect on interactive elements
    const addHoverListeners = () => {
        const interactiveElements = document.querySelectorAll(
            'a, button, .btn, input, textarea, select, [role="button"], ' +
            '.team-card, .blog-card, .perk-card, .feature-card, .strategy-card, ' +
            '.risk-card, .metric-card, .nav-link, .card, .allocation-item, ' +
            '.process-step, .risk-metric, .benchmark-item'
        );
        
        interactiveElements.forEach(el => {
            if (!el.hasAttribute('data-cursor-hover')) {
                el.setAttribute('data-cursor-hover', 'true');
                el.addEventListener('mouseenter', () => {
                    cursor.classList.add('hover');
                    cursor.classList.add('active');
                });
                el.addEventListener('mouseleave', () => {
                    cursor.classList.remove('hover');
                });
            }
        });
    };
    
    // Add listeners to existing elements
    addHoverListeners();
    
    // Watch for dynamically added elements
    const observer = new MutationObserver((mutations) => {
        let shouldAddListeners = false;
        mutations.forEach((mutation) => {
            if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                shouldAddListeners = true;
            }
        });
        if (shouldAddListeners) {
            addHoverListeners();
        }
    });
    
    observer.observe(document.body, { childList: true, subtree: true });
    
    // Click effect
    document.addEventListener('mousedown', () => cursor.classList.add('clicking'));
    document.addEventListener('mouseup', () => cursor.classList.remove('clicking'));
    
    // Pause when tab is hidden
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            isActive = false;
            if (rafId) cancelAnimationFrame(rafId);
        } else {
            isActive = true;
            updateCursor();
        }
    });
    
    // Cleanup on page unload
    window.addEventListener('beforeunload', () => {
        isActive = false;
        if (rafId) cancelAnimationFrame(rafId);
        observer.disconnect();
    });
}

// Button Ripple Effect
function createRipple(event) {
    const button = event.currentTarget;
    const circle = document.createElement('span');
    const diameter = Math.max(button.clientWidth, button.clientHeight);
    const radius = diameter / 2;
    
    const rect = button.getBoundingClientRect();
    
    circle.style.width = circle.style.height = diameter + 'px';
    circle.style.left = (event.clientX - rect.left - radius) + 'px';
    circle.style.top = (event.clientY - rect.top - radius) + 'px';
    circle.classList.add('ripple');
    
    const existingRipple = button.querySelector('.ripple');
    if (existingRipple) {
        existingRipple.remove();
    }
    
    button.appendChild(circle);
}

// Add ripple to all animated buttons
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.btn-animated, .btn-hero-primary, .btn-hero-secondary, .btn-cta').forEach(btn => {
        btn.addEventListener('click', createRipple);
    });
});

// Smooth scroll polyfill for older browsers
if (!('scrollBehavior' in document.documentElement.style)) {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                const headerOffset = 80;
                const elementPosition = target.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - headerOffset;
                
                window.scrollTo({
                    top: offsetPosition,
                    behavior: 'smooth'
                });
            }
        });
    });
}
