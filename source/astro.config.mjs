import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import sitemap from '@astrojs/sitemap';
import { readFileSync } from 'node:fs';
import { satteri } from '@astrojs/markdown-satteri';

const sidebar=JSON.parse(readFileSync(new URL('./generated-sidebar.json',import.meta.url),'utf8'));
export default defineConfig({
  site:'https://mizan0515.github.io',
  base:'/wuwa-quests',
  trailingSlash:'never',
  build:{format:'file'},
  markdown:{processor:satteri({features:{smartPunctuation:false}})},
  integrations:[sitemap({
    filter:(page)=>! /\/404(?:\.html)?\/?$/.test(new URL(page).pathname),
    serialize(item){
      const url=new URL(item.url);
      const pathname=url.pathname.replace(/\/$/,'');
      url.pathname=pathname==='/wuwa-quests'?pathname+'/index.html':pathname.endsWith('.html')?pathname:pathname+'.html';
      return {...item,url:url.href};
    },
  }),starlight({
    title:'명조 이야기 자료집',
    description:'퀘스트 대사와 인물·문서·세계관 설정을 근거 원문과 함께 이어 읽는 비공식 자료집',
    locales:{root:{label:'한국어',lang:'ko'}},
    defaultLocale:'root',
    sidebar,
    tableOfContents:{minHeadingLevel:2,maxHeadingLevel:2},
    pagination:false,
    lastUpdated:false,
    customCss:['./src/styles/quest.css','./src/styles/lore.css','./src/styles/atlas.css','./src/styles/reading-system.css','./src/lib/reading-kit/reading.css','./src/lib/reading-kit/reader.css','./src/lib/reading-kit/search-dialog.css','./src/lib/reading-kit/cva.css'],
    components:{Head:'./src/components/Head.astro',Footer:'./src/components/Footer.astro',Sidebar:'./src/components/Sidebar.astro',PageTitle:'./src/components/PageTitle.astro',Search:'./src/components/Search.astro'},
    expressiveCode:false,
    credits:true,
  })],
});
