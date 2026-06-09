/**
 * 职位猎手 - Popup Script（使用 executeScript 注入，不依赖 content_scripts）
 */

const BOSS_SCRIPT = `
(function() {
  const COLLECTOR_URL = 'http://localhost:8765/collect';
  const STORAGE_KEY = 'jh_ext_collected';

  // 尝试多种选择器
  const selectors = [
    '.job-card-wrapper', '.job-card', 'li.job-card-box', '[class*="job-card"]',
    '.job-primary', '.search-job-result li', '.recommend-job-card',
  ];
  let cards = [];
  for (const sel of selectors) {
    cards = document.querySelectorAll(sel);
    if (cards.length > 0) break;
  }
  if (cards.length === 0) {
    cards = document.querySelectorAll('a[href*="job_detail"]');
  }

  const jobs = [];
  cards.forEach(card => {
    const getText = (sels) => { for (const s of sels) { const e = card.querySelector(s); if (e && e.textContent.trim()) return e.textContent.trim(); } return ''; };
    const title = getText(['.job-name','.job-title','h3','.name','a[href*="job_detail"]','[class*="job-name"]','[class*="job-title"]']);
    const company = getText(['.company-name','.company-text','.com-name','.cname','[class*="company-name"]']);
    const salary = getText(['.salary','.red','.job-salary','.salary-text','[class*="salary"]']);
    const location = getText(['.job-area','.location','.area','[class*="area"]']);
    let url = card.href || '';
    if (!url) { const a = card.querySelector('a[href*="job_detail"]'); if (a) url = a.href; }
    if (title && company) jobs.push({ source_platform:'boss', job_url:url, title, company, salary, location });
  });
  return JSON.stringify({ count: jobs.length, jobs });
})();
`;

function injectAndCollect() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || tabs.length === 0) return setStatus('未找到页面');
    const tab = tabs[0];
    if (!tab.url || (!tab.url.includes('zhipin.com') && !tab.url.includes('liepin.com'))) {
      return setStatus('请打开Boss直聘/猎聘');
    }

    setStatus('采集中...');
    chrome.scripting.executeScript(
      { target: { tabId: tab.id }, func: () => {
        const selectors = [
          '.job-card-wrapper', '.job-card', 'li.job-card-box', '[class*="job-card"]',
          '.job-primary', '.search-job-result li', '.recommend-job-card',
        ];
        let cards = document.querySelectorAll(selectors[0]);
        for (const sel of selectors) {
          cards = document.querySelectorAll(sel);
          if (cards.length > 1) break;
        }
        if (cards.length <= 1) cards = document.querySelectorAll('a[href*="job_detail"]');

        const rows = [];
        cards.forEach(card => {
          const t = (card.querySelector('.job-name')||card.querySelector('.job-title')||card.querySelector('h3')||{});
          const c = (card.querySelector('.company-name')||card.querySelector('.company-text')||card.querySelector('.com-name')||{});
          const s = (card.querySelector('.salary')||card.querySelector('.red')||{});
          const l = (card.querySelector('.job-area')||card.querySelector('.area')||{});
          const title = (t.textContent||'').trim();
          const company = (c.textContent||'').trim();
          if (title && company) {
            let url = card.href || '';
            if (!url) { const a = card.querySelector('a[href*="job_detail"]'); if (a) url = a.href; }
            rows.push({ source_platform:'boss', job_url:url, title, company, salary:(s.textContent||'').trim(), location:(l.textContent||'').trim(), description:'' });
          }
        });
        return { selector_count: cards.length, job_count: rows.length, jobs: rows };
      }},
      (results) => {
        if (chrome.runtime.lastError) {
          setStatus('请刷新Boss页面后重试');
          return;
        }
        const data = results[0].result;
        setStatus(`找到 ${data.job_count} 个`);
        document.getElementById('count').textContent = data.job_count;

        // 发送到 collector
        data.jobs.forEach(job => {
          fetch('http://localhost:8765/collect', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify(job),
          }).catch(() => {});
        });
      }
    );
  });
}

function injectAndScan() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || tabs.length === 0) return setStatus('未找到页面');
    const tab = tabs[0];
    if (!tab.url || !tab.url.includes('zhipin.com')) return setStatus('仅支持Boss直聘');
    setStatus('扫描中...');

    chrome.scripting.executeScript(
      { target: { tabId: tab.id }, func: async () => {
        let total = 0;
        for (let page = 1; page <= 10; page++) {
          await new Promise(r => setTimeout(r, 2000));
          const selectors = ['.job-card-wrapper','[class*="job-card"]','.job-primary'];
          let cards = document.querySelectorAll(selectors[0]);
          for (const sel of selectors) { cards = document.querySelectorAll(sel); if (cards.length > 1) break; }
          cards.forEach(card => {
            const t = (card.querySelector('.job-name')||card.querySelector('.job-title')||{});
            const c = (card.querySelector('.company-name')||card.querySelector('.company-text')||{});
            const s = (card.querySelector('.salary')||card.querySelector('.red')||{});
            const title = (t.textContent||'').trim();
            const company = (c.textContent||'').trim();
            if (title && company) {
              let url = card.href || '';
              if (!url) { const a = card.querySelector('a[href*="job_detail"]'); if (a) url = a.href; }
              fetch('http://localhost:8765/collect', {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ source_platform:'boss', job_url:url, title, company, salary:(s.textContent||'').trim(), location:'', description:'' }),
              });
              total++;
            }
          });
          const next = document.querySelector('.options-pages .next, .page-next, [class*="page-next"]');
          if (!next || next.classList.contains('disabled')) break;
          next.click();
          await new Promise(r => setTimeout(r, 3000));
        }
        return total;
      }},
      (results) => {
        if (chrome.runtime.lastError) {
          setStatus('请刷新Boss页面后重试');
          return;
        }
        setStatus(`扫描完成`);
        document.getElementById('count').textContent = results[0].result;
      }
    );
  });
  window.close();
}

function setStatus(msg) {
  document.getElementById('status').textContent = msg;
}

document.getElementById('btnCollect').addEventListener('click', injectAndCollect);
document.getElementById('btnScanAll').addEventListener('click', injectAndScan);

document.getElementById('btnClear').addEventListener('click', () => {
  document.getElementById('count').textContent = '0';
  setStatus('已清除');
});

setStatus('就绪');
