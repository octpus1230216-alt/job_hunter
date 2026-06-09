/**
 * 职位猎手 - Background Service Worker
 */

let totalCollected = 0;
let isScanning = false;

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg.type === 'jobCollected') {
    totalCollected = msg.data.total;
    // 更新扩展图标徽章
    chrome.action.setBadgeText({ text: String(totalCollected) });
    chrome.action.setBadgeBackgroundColor({ color: '#07c160' });
  }

  if (msg.type === 'scanComplete') {
    isScanning = false;
    chrome.action.setBadgeText({ text: 'OK' });
    setTimeout(() => chrome.action.setBadgeText({ text: String(totalCollected) }), 2000);
  }

  if (msg.type === 'init') {
    chrome.action.setBadgeText({ text: String(totalCollected) });
    chrome.action.setBadgeBackgroundColor({ color: '#07c160' });
  }
});
