/**
 * 职位猎手 - Popup Script
 */

document.getElementById('btnCollect').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.tabs.sendMessage(tab.id, { action: 'collectCurrent' }, (resp) => {
    if (resp) {
      document.getElementById('status').textContent = `已采集 ${resp.count} 个`;
      document.getElementById('count').textContent = resp.total;
    } else {
      document.getElementById('status').textContent = '请打开Boss直聘/猎聘页面';
    }
  });
});

document.getElementById('btnScanAll').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  chrome.tabs.sendMessage(tab.id, { action: 'scanAll' }, (resp) => {
    if (resp) {
      document.getElementById('status').textContent = '自动扫描中...';
    } else {
      document.getElementById('status').textContent = '仅支持Boss直聘搜索页';
    }
  });
  window.close();
});

document.getElementById('btnClear').addEventListener('click', () => {
  chrome.storage.local.set({ jh_extension_collected: [] });
  document.getElementById('count').textContent = '0';
  document.getElementById('status').textContent = '已清除';
});

// 初始化
async function init() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.id) {
    chrome.tabs.sendMessage(tab.id, { action: 'getStatus' }, (resp) => {
      if (resp) {
        document.getElementById('count').textContent = resp.total;
        document.getElementById('status').textContent = resp.scanning ? '扫描中...' : '就绪';
      }
    });
  }
}
init();
