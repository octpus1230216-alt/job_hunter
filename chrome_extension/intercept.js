/**
 * 职位猎手 - API 拦截器 (Main World)
 * 调试版：拦截所有 API 响应，发送原始数据到采集器
 */
(function() {
  'use strict';
  const COLLECTOR = 'http://localhost:8765/collect';
  let count = 0;

  function sendRaw(json, url) {
    // 发送原始数据到采集器调试端点
    fetch('http://localhost:8765/debug', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, data: json, time: Date.now() }),
    }).catch(() => {});
  }

  function tryExtract(json, url) {
    // 尝试多种Boss直聘的数据结构
    const tests = [
      // Boss直聘新版
      () => {
        const list = json?.zpData?.jobList || json?.data?.jobList || json?.result?.jobList;
        if (!list || !Array.isArray(list)) return [];
        return list.map(j => ({
          source_platform: 'boss',
          title: j.jobName || '',
          company: j.brandName || '',
          salary: j.salaryDesc || '',
          location: j.cityName || j.areaDistrict || '',
          job_url: j.encryptJobId ? `https://www.zhipin.com/job_detail/${j.encryptJobId}.html` : '',
          description: '',
        })).filter(j => j.title && j.company);
      },
      // Boss直聘旧版/其他结构
      () => {
        const str = JSON.stringify(json);
        if (!str.includes('encryptJobId') && !str.includes('jobName')) return [];
        const jobs = [];
        const find = (obj) => {
          if (!obj || typeof obj !== 'object') return;
          if (Array.isArray(obj)) { obj.forEach(find); return; }
          if (obj.encryptJobId || obj.jobName || obj.securityId) {
            jobs.push({
              source_platform: 'boss',
              title: obj.jobName || obj.jobTitle || obj.title || '',
              company: obj.brandName || obj.companyName || obj.company || '',
              salary: obj.salaryDesc || obj.salary || '',
              location: obj.cityName || obj.areaDistrict || obj.location || '',
              job_url: obj.encryptJobId ? `https://www.zhipin.com/job_detail/${obj.encryptJobId}.html` : '',
              description: '',
            });
          }
          Object.values(obj).forEach(find);
        };
        find(json);
        return jobs.filter(j => j.title && j.company);
      },
    ];

    for (const test of tests) {
      try {
        const jobs = test();
        if (jobs.length > 0) {
          jobs.forEach(j => {
            count++;
            fetch(COLLECTOR, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(j),
            }).catch(() => {});
          });
          return;
        }
      } catch(e) {}
    }
  }

  // 劫持 fetch
  const origFetch = window.fetch;
  window.fetch = function(...args) {
    const url = (typeof args[0] === 'string') ? args[0] : (args[0]?.url || '');
    return origFetch.apply(this, args).then(resp => {
      if (url && (url.includes('zhipin.com') || url.includes('liepin.com'))) {
        const clone = resp.clone();
        clone.text().then(text => {
          try {
            const json = JSON.parse(text);
            sendRaw(json, url);  // 调试：发送原始数据
            tryExtract(json, url);
          } catch(e) {}
        }).catch(() => {});
      }
      return resp;
    });
  };

  // 劫持 XMLHttpRequest
  const OrigXHR = window.XMLHttpRequest;
  window.XMLHttpRequest = function() {
    const xhr = new OrigXHR();
    const origOpen = xhr.open;
    let reqUrl = '';

    xhr.open = function(method, url, ...rest) {
      reqUrl = url;
      return origOpen.apply(this, [method, url, ...rest]);
    };

    xhr.addEventListener('load', function() {
      if (reqUrl && (reqUrl.includes('zhipin.com') || reqUrl.includes('liepin.com'))) {
        try {
          const json = JSON.parse(xhr.responseText);
          sendRaw(json, reqUrl);
          tryExtract(json, reqUrl);
        } catch(e) {}
      }
    });
    return xhr;
  };

  console.log('🔍 职位猎手 API 拦截器已激活 (调试模式)');
})();
