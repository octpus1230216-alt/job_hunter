/**
 * 职位猎手 - Content Script
 * 运行在 Boss直聘 / 猎聘 页面，自动采集职位信息
 */

const COLLECTOR_URL = 'http://localhost:8765/collect';
const STORAGE_KEY = 'jh_extension_collected';

let collectedUrls = new Set();
let isScanning = false;
let currentPage = 1;
let maxPages = 10;

// 加载已采集的 URL
chrome.storage.local.get([STORAGE_KEY], (result) => {
  const saved = result[STORAGE_KEY] || [];
  saved.forEach(url => collectedUrls.add(url));
});

// ============================================================
// 公共函数
// ============================================================
function getPlatform() {
  if (location.hostname.includes('zhipin.com')) return 'boss';
  if (location.hostname.includes('liepin.com')) return 'liepin';
  return 'unknown';
}

function sendToCollector(jobData) {
  if (collectedUrls.has(jobData.job_url)) return;

  fetch(COLLECTOR_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(jobData),
  })
    .then(resp => resp.json())
    .then(data => {
      if (data.status === 'ok') {
        collectedUrls.add(jobData.job_url);
        const arr = [...collectedUrls];
        chrome.storage.local.set({ [STORAGE_KEY]: arr });
        chrome.runtime.sendMessage({
          type: 'jobCollected',
          data: { company: jobData.company, title: jobData.title, total: arr.length }
        });
        showToast(`✅ ${arr.length}: ${jobData.company}`);
      }
    })
    .catch(() => {
      showToast('⚠️ 采集器未启动 (python collector_server.py)');
    });
}

function showToast(msg) {
  const toast = document.createElement('div');
  toast.style.cssText = 'position:fixed;top:20px;right:20px;background:#07c160;color:white;padding:10px 20px;border-radius:8px;z-index:99999;font-size:14px;box-shadow:0 2px 8px rgba(0,0,0,0.2);';
  toast.textContent = msg;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2500);
}

// ============================================================
// Boss 直聘 采集逻辑
// ============================================================
function extractBossJobFromCard(card) {
  const titleEl = card.querySelector('.job-name, .job-title');
  const companyEl = card.querySelector('.company-name, .company-text');
  const salaryEl = card.querySelector('.salary, .red');
  const locEl = card.querySelector('.job-area, .location');
  const urlEl = card.querySelector('a');

  let jobUrl = '';
  if (urlEl && urlEl.href) {
    jobUrl = urlEl.href.split('?')[0].split('#')[0];
    // 转换详情页URL为标准格式
    if (jobUrl.includes('/job_detail/')) {
      const match = jobUrl.match(/job_detail\/([a-zA-Z0-9]+)/);
      if (match) jobUrl = `https://www.zhipin.com/job_detail/${match[1]}.html`;
    }
  }

  return {
    source_platform: 'boss',
    job_url: jobUrl,
    title: titleEl ? titleEl.textContent.trim() : '',
    company: companyEl ? companyEl.textContent.trim() : '',
    salary: salaryEl ? salaryEl.textContent.trim() : '',
    location: locEl ? locEl.textContent.trim() : '',
  };
}

function collectCurrentBossPage() {
  const cards = document.querySelectorAll('.job-card-wrapper, .job-card');
  let count = 0;

  cards.forEach(card => {
    const job = extractBossJobFromCard(card);
    if (job.title && job.company && job.job_url) {
      sendToCollector(job);
      count++;
    }
  });

  return count;
}

async function scanAllBossPages() {
  if (isScanning) return;
  isScanning = true;
  currentPage = 1;

  showToast(`🔍 开始自动扫描...`);

  while (currentPage <= maxPages) {
    await sleep(2000);
    const count = collectCurrentBossPage();
    showToast(`📄 第${currentPage}页: 采集 ${count} 个 (共 ${collectedUrls.size})`);

    // 翻页
    const nextBtn = document.querySelector('.options-pages .next, .page-next');
    if (!nextBtn || nextBtn.classList.contains('disabled')) {
      showToast(`✅ 扫描完成！共 ${collectedUrls.size} 个`);
      break;
    }
    nextBtn.click();
    currentPage++;
    await sleep(3000); // 等待页面加载
  }

  isScanning = false;
  chrome.runtime.sendMessage({ type: 'scanComplete', data: { total: collectedUrls.size } });
}

// ============================================================
// 猎聘 采集逻辑
// ============================================================
function extractLiepinJobFromCard(card) {
  const titleEl = card.querySelector('.job-title, h3');
  const companyEl = card.querySelector('.company-name');
  const salaryEl = card.querySelector('.job-salary, .salary');
  const locEl = card.querySelector('.job-dq, .location');
  const urlEl = card.querySelector('a');

  return {
    source_platform: 'liepin',
    job_url: urlEl ? urlEl.href : '',
    title: titleEl ? titleEl.textContent.trim() : '',
    company: companyEl ? companyEl.textContent.trim() : '',
    salary: salaryEl ? salaryEl.textContent.trim() : '',
    location: locEl ? locEl.textContent.trim() : '',
  };
}

function collectCurrentLiepinPage() {
  const cards = document.querySelectorAll('.job-list-item, .job-card');
  let count = 0;

  cards.forEach(card => {
    const job = extractLiepinJobFromCard(card);
    if (job.title && job.company) {
      sendToCollector(job);
      count++;
    }
  });

  return count;
}

// ============================================================
// 监听来自 popup 的消息
// ============================================================
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'collectCurrent') {
    const platform = getPlatform();
    let count = 0;
    if (platform === 'boss') count = collectCurrentBossPage();
    else if (platform === 'liepin') count = collectCurrentLiepinPage();
    sendResponse({ count, total: collectedUrls.size });
  }

  if (msg.action === 'scanAll') {
    if (getPlatform() === 'boss') scanAllBossPages();
    sendResponse({ status: 'started' });
  }

  if (msg.action === 'getStatus') {
    sendResponse({ total: collectedUrls.size, scanning: isScanning });
  }
});

// ============================================================
// 工具函数
// ============================================================
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// 初始化
console.log('🔍 职位猎手扩展已激活');
chrome.runtime.sendMessage({ type: 'init', data: { url: location.href } });
