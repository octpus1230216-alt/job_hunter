/**
 * Injector - 通过 script 标签注入拦截代码到页面主世界
 * 这是最可靠的 MAIN world 注入方式
 */
const script = document.createElement('script');
script.textContent = `(${function() {
  const COLLECTOR = 'http://localhost:8765/collect';
  const sent = new Set();
  let count = 0;

  function send(job) {
    const key = job.job_url || (job.company + job.title);
    if (sent.has(key)) return;
    sent.add(key);
    fetch(COLLECTOR, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(job),
    }).catch(() => {});
  }

  function debug(url, data) {
    fetch('http://localhost:8765/debug', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, snippet: JSON.stringify(data).slice(0, 300), time: Date.now() }),
    }).catch(() => {});
  }

  function extract(json, url) {
    const d = json?.zpData?.jobList || json?.data?.jobList || json?.zpData?.result || json?.result?.data;
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
    // 尝试遍历寻找职位数据
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
          try { const j = JSON.parse(t); debug(url, j); extract(j, url); } catch(e) {}
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
        debug(u, j);
        extract(j, u);
      } catch(e) {}
    });
    return x;
  };

  console.log('[JobHunter] 拦截器已激活');
}})();`;

script.onload = function() { this.remove(); };
document.documentElement.appendChild(script);
