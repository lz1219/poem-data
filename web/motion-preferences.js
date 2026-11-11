(function () {
  const key = 'library-motion';
  const allowed = ['full', 'gentle', 'still'];
  let initial = 'gentle';
  try { const saved = localStorage.getItem(key); if (allowed.includes(saved)) initial = saved; } catch (_) {}
  document.documentElement.dataset.motion = initial;
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-motion-setting]').forEach(control => {
      control.value = initial;
      control.addEventListener('change', () => {
        if (!allowed.includes(control.value)) return;
        document.documentElement.dataset.motion = control.value;
        try { localStorage.setItem(key, control.value); } catch (_) {}
      });
    });
  });
})();
