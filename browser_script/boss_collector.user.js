// ==UserScript==
// @name         职位猎手 - Boss直聘采集器
// @namespace    job-hunter
// @version      1.0
// @description  浏览Boss直聘时自动收集职位信息到本地工具
// @author       Job Hunter
// @match        https://www.zhipin.com/web/geek/job*
// @match        https://www.zhipin.com/job_detail/*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// ==/UserScript==

(function() {
    'use strict';

    const COLLECTOR_URL = 'http://localhost:8765/collect';
    const collectedUrls = new Set();

    // 从localStorage恢复已收集的URL
    try {
        const saved = JSON.parse(localStorage.getItem('jh_collected_urls') || '[]');
        saved.forEach(url => collectedUrls.add(url));
    } catch(e) {}

    function saveCollected() {
        localStorage.setItem('jh_collected_urls', JSON.stringify([...collectedUrls]));
    }

    function sendToCollector(jobData) {
        if (collectedUrls.has(jobData.job_url)) return;

        GM_xmlhttpRequest({
            method: 'POST',
            url: COLLECTOR_URL,
            headers: { 'Content-Type': 'application/json' },
            data: JSON.stringify(jobData),
            onload: function(resp) {
                if (resp.status === 200) {
                    collectedUrls.add(jobData.job_url);
                    saveCollected();
                    console.log('✅ 已采集:', jobData.company, '-', jobData.title);
                    showToast('✅ 已采集: ' + jobData.company);
                }
            },
            onerror: function() {
                console.log('⚠️ 采集接收器未启动 (localhost:8765)');
            }
        });
    }

    function showToast(msg) {
        const toast = document.createElement('div');
        toast.style.cssText = 'position:fixed;top:20px;right:20px;background:#07c160;color:white;padding:10px 20px;border-radius:8px;z-index:99999;font-size:14px;box-shadow:0 2px 8px rgba(0,0,0,0.2);';
        toast.textContent = msg;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 2000);
    }

    // 从页面提取职位信息
    function extractJob() {
        const url = window.location.href;
        let data = { source_platform: 'boss', job_url: url };

        // 职位标题
        const titleEl = document.querySelector('.job-name, .name, h1');
        if (titleEl) data.title = titleEl.textContent.trim();

        // 公司名
        const companyEl = document.querySelector('.company-name, .name');
        if (companyEl) data.company = companyEl.textContent.trim();

        // 薪资
        const salaryEl = document.querySelector('.salary, .job-salary');
        if (salaryEl) data.salary = salaryEl.textContent.trim();

        // 地点
        const locEl = document.querySelector('.location, .job-location');
        if (locEl) data.location = locEl.textContent.trim();

        // JD内容
        const jdEl = document.querySelector('.job-detail, .job-sec, .detail-content');
        if (jdEl) data.description = jdEl.textContent.trim().substring(0, 5000);

        return data;
    }

    // 在搜索结果页面添加采集按钮
    function addCollectButtons() {
        const cards = document.querySelectorAll('.job-card-wrapper, .job-card');
        cards.forEach(card => {
            if (card.querySelector('.jh-collect-btn')) return;

            const btn = document.createElement('button');
            btn.className = 'jh-collect-btn';
            btn.textContent = '📥 采集';
            btn.style.cssText = 'position:absolute;top:8px;right:8px;background:#07c160;color:white;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:12px;z-index:10;';
            btn.onclick = function(e) {
                e.stopPropagation();
                e.preventDefault();

                const titleEl = card.querySelector('.job-name, .job-title');
                const companyEl = card.querySelector('.company-name, .company-text');
                const salaryEl = card.querySelector('.salary, .red');
                const urlEl = card.querySelector('a');

                const jobData = {
                    source_platform: 'boss',
                    job_url: urlEl ? urlEl.href : window.location.href,
                    title: titleEl ? titleEl.textContent.trim() : '',
                    company: companyEl ? companyEl.textContent.trim() : '',
                    salary: salaryEl ? salaryEl.textContent.trim() : '',
                    location: '',
                    description: '',
                };

                sendToCollector(jobData);
            };
            card.style.position = 'relative';
            card.appendChild(btn);
        });
    }

    // 页面加载后执行
    function init() {
        console.log('🔍 职位猎手已激活 — 浏览Boss直聘时自动采集');

        // 详情页自动采集
        if (window.location.href.includes('/job_detail/')) {
            setTimeout(() => {
                const job = extractJob();
                if (job.title) sendToCollector(job);
            }, 2000);
        }

        // 列表页添加采集按钮
        if (window.location.href.includes('/web/geek/job')) {
            setInterval(addCollectButtons, 3000);
        }
    }

    // 页面加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
