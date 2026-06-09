/**
 * 职位猎手 - 双重注入方案
 * Part 1: script标签注入到MAIN world，拦截API
 * Part 2: content script监听postMessage，中转数据到localhost
 */

// ============================================================
// Part 1: 注入 script 到页面主世界
// ============================================================
const script = document.createElement('script');
script.textContent = `(${function() {
  let count = 0;

  function send(job) {
    window.postMessage({ type: 'JOB_HUNTER_JOB', data: job }, '*');
  }

  function debug(url, snippet) {
    window.postMessage({ type: 'JOB_HUNTER_DEBUG', data: { url, snippet, time: Date.now() } }, '*');
  }

  function extract(json, url) {
    const d = json?.zpData?.jobList || json?.data?.jobList || json?.result?.jobList
          || json?.zpData?.result || json?.result?.data;
    if (d && Array.isArray(d)) {
      d.forEach(j => {
        if (j.jobName && j.brandName) {
          send({
            source_platform: 'boss',
            title: j.jobName, company: j.brandName,
            salary: j.salaryDesc || '', location: j.cityName || '',
            job_url: j.encryptJobId ? 'https://www.zhipin.com/job_detail/'+j.encryptJobId+'.html' : '',
            description: '',
          });
        }
      });
      return;
    }
    try {
      const s = JSON.stringify(json);
      if (s.includes('encryptJobId') || s.includes('jobName') || s.includes('securityId')) {
        const find = (obj) => {
          if (!obj || typeof obj !== 'object') return;
          if (Array.isArray(obj)) { obj.forEach(find); return; }
          if ((obj.encryptJobId || obj.securityId) && obj.jobName) {
            send({
              source_platform: 'boss',
              title: obj.jobName || obj.title || '',
              company: obj.brandName || obj.company || '',
              salary: obj.salaryDesc || '',
              location: obj.cityName || '',
              job_url: obj.encryptJobId ? 'https://www.zhipin.com/job_detail/'+obj.encryptJobId+'.html' : '',
              description: '',
            });
          }
          Object.values(obj).forEach(find);
        };
        find(json);
      }
    } catch(e) {}
  }

  // Hook fetch
  const _fetch = window.fetch;
  window.fetch = function() {
    const url = (typeof arguments[0] === 'string') ? arguments[0] : (arguments[0]?.url || '');
    return _fetch.apply(this, arguments).then(r => {
      if (r && r.clone) {
        r.clone().text().then(t => {
          try { const j = JSON.parse(t); debug(url, JSON.stringify(j).slice(0,300)); extract(j, url); } catch(e) {}
        }).catch(()=>{});
      }
      return r;
    });
  };

  // Hook XHR
  const XHR = window.XMLHttpRequest;
  window.XMLHttpRequest = function() {
    const x = new XHR();
    const _open = x.open;
    let u = '';
    x.open = function(m, url) { u = url; return _open.apply(this, arguments); };
    x.addEventListener('load', function() {
      try {
        const j = JSON.parse(x.responseText);
        debug(u, JSON.stringify(j).slice(0,300));
        extract(j, u);
      } catch(e) {}
    });
    return x;
  };

  console.log('[JobHunter] 拦截器已激活');
}})();`;

script.onload = function() { this.remove(); };
document.documentElement.appendChild(script);


// ============================================================
// Part 2: content script 监听 postMessage，中转数据到 localhost
// ============================================================
const sent = new Set();

window.addEventListener('message', (event) => {
  if (event.source !== window) return;

  const msg = event.data;
  if (!msg || !msg.type) return;

  if (msg.type === 'JOB_HUNTER_JOB') {
    const job = msg.data;
    const key = job.job_url || (job.company + job.title);
    if (sent.has(key)) return;
    sent.add(key);

    fetch('http://localhost:8765/collect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(job),
    }).catch(() => {});
  }

  if (msg.type === 'JOB_HUNTER_DEBUG') {
    fetch('http://localhost:8765/debug', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(msg.data),
    }).catch(() => {});
  }
});
