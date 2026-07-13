// ==UserScript==
// @name         职位猎手 - 猎聘采集器
// @namespace    job-hunter
// @version      1.0
// @description  浏览猎聘时自动收集职位信息到本地工具
// @author       Job Hunter
// @match        https://www.liepin.com/job/*
// @match        https://www.liepin.com/zhaopin/*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// ==/UserScript==

(function() {
    'use strict';

    const COLLECTOR_URL = 'http://localhost:8765/collect';
    const collectedUrls = new Set();

    try {
        const saved = JSON.parse(localStorage.getItem('jh_liepin_collected') || '[]');
        saved.forEach(url => collectedUrls.add(url));
    } catch(e) {}

    function saveCollected() {
        localStorage.setItem('jh_liepin_collected', JSON.stringify([...collectedUrls]));
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
                    console.log('✅ 已采集(猎聘):', jobData.company, '-', jobData.title);
                }
            },
            onerror: function() {
                console.log('⚠️ 采集接收器未启动');
            }
        });
    }

    function extractJob() {
        const url = window.location.href;
        let data = { source_platform: 'liepin', job_url: url };

        const titleEl = document.querySelector('.job-title, h1, .title-info h1');
        if (titleEl) data.title = titleEl.textContent.trim();

        const companyEl = document.querySelector('.company-name, .company-title');
        if (companyEl) data.company = companyEl.textContent.trim();

        const salaryEl = document.querySelector('.job-salary, .salary');
        if (salaryEl) data.salary = salaryEl.textContent.trim();

        const locEl = document.querySelector('.job-detail-box .basic-info li, .job-location');
        if (locEl) data.location = locEl.textContent.trim();

        const jdEl = document.querySelector('.job-description, .job-detail, .content-word');
        if (jdEl) data.description = jdEl.textContent.trim().substring(0, 5000);

        return data;
    }

    function init() {
        console.log('🔍 职位猎手(猎聘)已激活');

        if (window.location.href.includes('/job/')) {
            setTimeout(() => {
                const job = extractJob();
                if (job.title) sendToCollector(job);
            }, 2000);
        }

        // 列表页添加采集按钮
        if (window.location.href.includes('/zhaopin/')) {
            setInterval(() => {
                const cards = document.querySelectorAll('.job-list-item, .job-card');
                cards.forEach(card => {
                    if (card.querySelector('.jh-collect-btn')) return;

                    const btn = document.createElement('button');
                    btn.className = 'jh-collect-btn';
                    btn.textContent = '📥 采集';
                    btn.style.cssText = 'position:absolute;top:8px;right:8px;background:#07c160;color:white;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:12px;z-index:10;';
                    btn.onclick = function(e) {
                        e.stopPropagation();
                        e.preventDefault();
                        const titleEl = card.querySelector('.job-title, h3');
                        const companyEl = card.querySelector('.company-name');
                        const urlEl = card.querySelector('a');
                        sendToCollector({
                            source_platform: 'liepin',
                            job_url: urlEl ? urlEl.href : '',
                            title: titleEl ? titleEl.textContent.trim() : '',
                            company: companyEl ? companyEl.textContent.trim() : '',
                            salary: '', location: '', description: '',
                        });
                    };
                    card.style.position = 'relative';
                    card.appendChild(btn);
                });
            }, 3000);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
