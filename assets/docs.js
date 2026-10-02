"use strict";
const root=document.documentElement,theme=document.querySelector('#theme-toggle');
function setTheme(dark){root.dataset.theme=dark?'dark':'light';theme.textContent=dark?'밝게':'어둡게';theme.setAttribute('aria-pressed',String(dark));}
try{setTheme(localStorage.getItem('wuwa-theme')==='dark');}catch(_){setTheme(false);}
theme.addEventListener('click',()=>{const dark=root.dataset.theme!=='dark';setTheme(dark);try{localStorage.setItem('wuwa-theme',dark?'dark':'light');}catch(_){}});
const menu=document.querySelector('#site-navigation');if(matchMedia('(max-width:760px)').matches)menu.open=false;
const current=document.querySelector('.nav-page.current');if(current)current.scrollIntoView({block:'nearest'});
const links=[...document.querySelectorAll('.page-toc a')];if('IntersectionObserver' in window&&links.length){const observer=new IntersectionObserver(entries=>{for(const entry of entries){if(entry.isIntersecting){for(const link of links)link.classList.toggle('active',link.hash==='#'+entry.target.id);}}},{rootMargin:'-100px 0px -60% 0px'});document.querySelectorAll('.scene').forEach(scene=>observer.observe(scene));}

const lineToggle=document.querySelector('#line-toggle');if(lineToggle)lineToggle.addEventListener('click',()=>{const show=root.dataset.lineIds!=='true';root.dataset.lineIds=String(show);lineToggle.setAttribute('aria-pressed',String(show));lineToggle.textContent=show?'대사 번호 숨기기':'대사 번호 보기';});
const path=location.pathname;document.querySelectorAll('.nav-home').forEach(a=>{if(new URL(a.href).pathname===path)a.setAttribute('aria-current','page');});
function updateIndexNav(){if(!document.querySelector('#version'))return;const version=document.querySelector('#version').value,kind=document.querySelector('#type').value;document.querySelectorAll('.nav-version').forEach(d=>{d.open=d.querySelector('summary').textContent===version;});document.querySelectorAll('.nav-category').forEach(a=>{const p=new URL(a.href).searchParams;a.classList.toggle('selected-category',p.get('version')===version&&p.get('type')===kind);});}
document.addEventListener('filters-changed',updateIndexNav);updateIndexNav();
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();document.querySelector('#global-q').focus();}});
