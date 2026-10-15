/* Theme toggle and shared Chart.js defaults. */

function setTheme(mode) {
    document.documentElement.setAttribute('data-theme', mode);
    try { localStorage.setItem('cap_theme', mode); } catch (e) { /* private mode */ }
    location.reload();
}

function toggleTheme() {
    var now = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    setTheme(now);
}

function themeColours() {
    var css = getComputedStyle(document.documentElement);
    return {
        ink: css.getPropertyValue('--ink').trim(),
        ink2: css.getPropertyValue('--ink-2').trim(),
        border: css.getPropertyValue('--border').trim(),
        accent: css.getPropertyValue('--accent').trim(),
        good: css.getPropertyValue('--good').trim(),
        bad: css.getPropertyValue('--bad').trim(),
        warn: css.getPropertyValue('--warn').trim()
    };
}

if (window.Chart) {
    var c = themeColours();
    Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = c.ink2;
    Chart.defaults.borderColor = c.border;
    Chart.defaults.plugins.legend.labels.boxWidth = 12;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.maintainAspectRatio = false;
}
