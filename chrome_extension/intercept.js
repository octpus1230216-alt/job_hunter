/**
 * 职位猎手 - API 拦截器 (Main World)
 * 在 Boss直聘 JavaScript 运行前注入，劫持 fetch/XHR
 */
(function() {
  'use strict';
  const COLLECTOR = 'http://localhost:8765/collect';
  const sent = new Set();

  function sendJob(job) {
    const key = job.job_url || (job.company + job.title);
    if (sent.has(key)) return;
    sent.add(key);
    fetch(COLLECTOR, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(job),
    }).catch(() => {});
  }

  function extractJobs(obj) {
    const results = [];
    if (!obj || typeof obj !== 'object') return results;

    // 递归搜索所有数组字段
    const search = (o) => {
      if (!o || typeof o !== 'object') return;
      if (Array.isArray(o)) {
        for (const item of o) {
          if (item && typeof item === 'object') {
            const title = item.jobName || item.job_name || item.jobTitle || item.title || '';
            const company = item.brandName || item.brand_name || item.companyName || item.company_name || item.company || '';
            if (title && company) {
              results.push({
                source_platform: 'boss',
                job_url: item.encryptJobId ? `https://www.zhipin.com/job_detail/${item.encryptJobId}.html` : '',
                title: String(title),
                company: String(company),
                salary: item.salaryDesc || item.salary_desc || item.salary || '',
                location: item.cityName || item.city_name || item.areaDistrict || '',
                description: item.jobDescription || item.job_description || '',
              });
            }
          }
          search(item);
        }
      } else if (typeof o === 'object') {
        for (const v of Object.values(o)) search(v);
      }
    };
    search(obj);
    return results;
  }

  // 劫持 fetch
  const origFetch = window.fetch;
  window.fetch = function(...args) {
    const url = typeof args[0] === 'string' ? args[0] : args[0].url;
    return origFetch.apply(this, args).then(resp => {
      if (url.includes('zhipin.com') || url.includes('liepin.com')) {
        const clone = resp.clone();
        clone.json().then(json => {
          const jobs = extractJobs(json);
          jobs.forEach(sendJob);
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

    const origSend = xhr.send;
    xhr.send = function(...args) {
      xhr.addEventListener('load', function() {
        if (reqUrl.includes('zhipin.com') || reqUrl.includes('liepin.com')) {
          try {
            const json = JSON.parse(xhr.responseText);
            const jobs = extractJobs(json);
            jobs.forEach(sendJob);
          } catch(e) {}
        }
      });
      return origSend.apply(this, args);
    };
    return xhr;
  };

  console.log('🔍 职位猎手 API 拦截器已激活');
})();
