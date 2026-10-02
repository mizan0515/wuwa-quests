import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { readFileSync } from 'node:fs';

const sidebar=JSON.parse(readFileSync(new URL('./generated-sidebar.json',import.meta.url),'utf8'));
export default defineConfig({
  site:'https://mizan0515.github.io',
  base:'/wuwa-quests',
  trailingSlash:'never',
  build:{format:'file'},
  integrations:[starlight({
    title:'명조 퀘스트 자료집',
    description:'버전·임무 종류별 한국어 퀘스트 대사와 선택지를 읽고 검색하는 비공식 자료집',
    locales:{root:{label:'한국어',lang:'ko'}},
    defaultLocale:'root',
    sidebar,
    tableOfContents:{minHeadingLevel:2,maxHeadingLevel:2},
    pagination:false,
    lastUpdated:false,
    customCss:['./src/styles/quest.css'],
    components:{Footer:'./src/components/Footer.astro'},
    expressiveCode:false,
    credits:true,
  })],
});
