document.getElementById('status').textContent = 'API拦截模式已激活';

document.getElementById('btnCollect').addEventListener('click', () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs[0]) return;
    chrome.scripting.executeScript({
      target: { tabId: tabs[0].id },
      func: () => {
        // 触发页面重新搜索（通过点击搜索按钮）
        const btn = document.querySelector('.btn-search, button[type="submit"], .search-btn');
        if (btn) { btn.click(); return '已触发重新搜索'; }
        // 或者刷新页面
        location.reload();
        return '已刷新页面';
      }
    });
  });
});

document.getElementById('btnScanAll').addEventListener('click', () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs[0]) return;
    chrome.scripting.executeScript({
      target: { tabId: tabs[0].id },
      func: async () => {
        for (let i = 1; i <= 10; i++) {
          await new Promise(r => setTimeout(r, 2500));
          const next = document.querySelector('.options-pages .next, [class*="page-next"], .page .next');
          if (!next || next.classList.contains('disabled')) break;
          next.click();
          await new Promise(r => setTimeout(r, 2000));
        }
        return '翻页完成';
      }
    });
  });
  window.close();
});

document.getElementById('btnClear').addEventListener('click', () => {
  document.getElementById('count').textContent = '0';
});

setInterval(() => {
  fetch('http://localhost:8765/jobs').then(r => r.json()).then(d => {
    document.getElementById('count').textContent = d.total || 0;
  }).catch(() => {});
}, 2000);
