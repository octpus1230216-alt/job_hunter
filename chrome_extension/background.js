/**
 * 职位猎手 - Background Service Worker
 * 检测到 Boss直聘/猎聘 页面时，自动注入 API 拦截脚本
 */

// 已注入的 tab，避免重复注入
const injectedTabs = new Set();

chrome.webNavigation.onCommitted.addListener((details) => {
  // 只处理主框架
  if (details.frameId !== 0) return;
  if (injectedTabs.has(details.tabId)) return;

  const url = details.url;
  if (!url.includes('zhipin.com') && !url.includes('liepin.com')) return;

  injectedTabs.add(details.tabId);

  chrome.scripting.executeScript({
    target: { tabId: details.tabId },
    world: 'MAIN',
    files: ['intercept.js'],
  }).then(() => {
    console.log('✅ API拦截器已注入:', url);
    chrome.action.setBadgeText({ text: 'ON', tabId: details.tabId });
    chrome.action.setBadgeBackgroundColor({ color: '#07c160' });
  }).catch(err => {
    console.log('⚠️ 注入失败:', err.message);
    injectedTabs.delete(details.tabId);
  });
});

// Tab 关闭时清理
chrome.tabs.onRemoved.addListener((tabId) => {
  injectedTabs.delete(tabId);
});
