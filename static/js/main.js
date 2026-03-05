// Переключатель темы (тёмная / светлая)
(function () {
    var STORAGE_KEY = 'chess-theme';
    var body = document.body;

    function getTheme() {
        return localStorage.getItem(STORAGE_KEY) || 'dark';
    }

    function setTheme(theme) {
        localStorage.setItem(STORAGE_KEY, theme);
        body.setAttribute('data-theme', theme);
        var iconDark = document.querySelector('.theme-icon-dark');
        var iconLight = document.querySelector('.theme-icon-light');
        if (iconDark && iconLight) {
            iconDark.classList.toggle('d-none', theme === 'light');
            iconLight.classList.toggle('d-none', theme !== 'light');
        }
    }

    body.setAttribute('data-theme', getTheme());

    document.addEventListener('DOMContentLoaded', function () {
        var btn = document.getElementById('themeToggle');
        if (btn) {
            setTheme(getTheme());
            btn.addEventListener('click', function () {
                var next = getTheme() === 'dark' ? 'light' : 'dark';
                setTheme(next);
            });
        }
    });
})();
