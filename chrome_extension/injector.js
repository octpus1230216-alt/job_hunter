/**
 * 职位猎手 - 终极调试版
 * 实际展示了拦截过程，让用户看到数据是否被拦截
 */
const script = document.createElement('script');
script.textContent = `(${function() {
  const sent = new Set();

  // 在页面顶部显示拦截状态条
  const bar = document.createElement('div');
  bar.id = '__jh_status';
  bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#07c160;color:white;text-align:center;padding:4px;font-size:13px;font-family:sans-serif;';
  bar.textContent = '🔍 职位猎手已激活 (等待API请求...)';
  document.documentElement.appendChild(bar);

  function updateStatus(msg) {
    const b = document.getElementById('__jh_status');
    if (b) b.textContent = msg;
  }

  function extract(json, url) {
    let found = 0;
    // Boss直聘 v1: zpData.jobList
    const list1 = json?.zpData?.jobList;
    if (list1 && Array.isArray(list1) && list1.length > 0) {
      list1.forEach(j => {
        if (j.jobName && j.brandName) {
          const key = j.encryptJobId || (j.brandName + j.jobName);
          if (sent.has(key)) return;
          sent.add(key);
          found++;
          window.postMessage({ __jh_job: {
            source_platform: 'boss',
            title: j.jobName, company: j.brandName,
            salary: j.salaryDesc || '', location: j.cityName || '',
            job_url: j.encryptJobId ? 'https://www.zhipin.com/job_detail/'+j.encryptJobId+'.html' : '',
            description: '',
          }}, '*');
        }
      });
    }
    if (found > 0) {
      updateStatus('✅ 拦截到 ' + found + ' 个职位 (共' + sent.size + ')');
      return;
    }
    // 通用递归
    try {
      const s = JSON.stringify(json);
      if (s.includes('encryptJobId') || s.includes('securityId')) {
        const find = (obj) => {
          if (!obj || typeof obj !== 'object') return;
          if (Array.isArray(obj)) { obj.forEach(find); return; }
          if (obj.encryptJobId || obj.securityId) {
            const key = obj.encryptJobId || obj.securityId;
            if (sent.has(key)) return;
            sent.add(key);
            found++;
            window.postMessage({ __jh_job: {
              source_platform: 'boss',
              title: obj.jobName || obj.title || '',
              company: obj.brandName || obj.company || '',
              salary: obj.salaryDesc || '',
              location: obj.cityName || '',
              job_url: obj.encryptJobId ? 'https://www.zhipin.com/job_detail/'+obj.encryptJobId+'.html' : '',
              description: '',
            }}, '*');
          }
          Object.values(obj).forEach(find);
        };
        find(json);
      }
    } catch(e) {}
    if (found > 0) updateStatus('✅ 拦截到 ' + found + ' 个职位');
  }

  // Hook fetch
  const _fetch = window.fetch;
  window.fetch = function() {
    const url = (typeof arguments[0] === 'string') ? arguments[0] : (arguments[0]?.url || '');
    return _fetch.apply(this, arguments).then(r => {
      if (r && r.clone && r.headers) {
        r.clone().text().then(t => {
          try { extract(JSON.parse(t), url); } catch(e) {}
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
      try { extract(JSON.parse(x.responseText), u); } catch(e) {}
    });
    return x;
  };
}})();`;

script.onload = function() { this.remove(); };
document.documentElement.appendChild(script);


// ============================================================
// Content script 监听 postMessage 并转发
// ============================================================
const sent = new Set();

window.addEventListener('message', (event) => {
  const job = event.data?.__jh_job;
  if (!job) return;

  const key = job.job_url || (job.company + job.title);
  if (sent.has(key)) return;
  sent.add(key);

  fetch('http://localhost:8765/collect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(job),
  }).then(() => {
    console.log('✅ 已发送到采集器:', job.company, job.title);
  }).catch(() => {
    console.log('⚠️ 采集器未启动');
  });
});
