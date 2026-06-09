/**
 * 职位猎手 - Popup Script
 */

function sendToTab(action, cb) {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || tabs.length === 0) {
      document.getElementById('status').textContent = '未找到活动标签页';
      return;
    }
    const tab = tabs[0];
    if (!tab.url || (!tab.url.includes('zhipin.com') && !tab.url.includes('liepin.com'))) {
      document.getElementById('status').textContent = '请打开Boss直聘/猎聘页面';
      return;
    }
    chrome.tabs.sendMessage(tab.id, { action }, (resp) => {
      if (chrome.runtime.lastError) {
        document.getElementById('status').textContent = '请刷新Boss直聘页面后重试';
        return;
      }
      if (cb) cb(resp);
    });
  });
}

document.getElementById('btnCollect').addEventListener('click', () => {
  document.getElementById('status').textContent = '采集中...';
  sendToTab('collectCurrent', (resp) => {
    if (resp) {
      document.getElementById('status').textContent = `已采集 ${resp.count} 个`;
      document.getElementById('count').textContent = resp.total;
    }
  });
});

document.getElementById('btnScanAll').addEventListener('click', () => {
  document.getElementById('status').textContent = '自动扫描中...';
  sendToTab('scanAll', (resp) => {
    if (resp) {
      document.getElementById('status').textContent = '扫描已启动，查看Boss页面';
    }
  });
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
