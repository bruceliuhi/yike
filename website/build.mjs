import { cp, mkdir, rm, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)));
const dist = join(root, 'dist');
const routes = ['products/workbench', 'products/crm', 'features', 'download', 'roadmap', 'contact'];
const titles = {
  home: '意客 AI｜把“有人在找”，变成今天能跟进的机会',
  'products/workbench': '商机工作台｜意客 AI',
  'products/crm': '客户情报 CRM｜意客 AI',
  features: '能力全景｜意客 AI',
  download: '下载与试用｜意客 AI',
  roadmap: '产品路线｜意客 AI',
  contact: '预约演示｜意客 AI',
};

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });
await cp(join(root, 'index.html'), join(dist, 'index.html'));
await cp(join(root, 'src'), join(dist, 'src'), { recursive: true });
await cp(join(root, 'public'), join(dist), { recursive: true });

const home = await (await import('node:fs/promises')).readFile(join(dist, 'index.html'), 'utf8');
for (const route of routes) {
  const html = home
    .replace('<title>意客 AI｜把“有人在找”，变成今天能跟进的机会</title>', `<title>${titles[route]}</title>`)
    .replace('data-page="home"', `data-page="${route.replaceAll('/', '-')}"`);
  const target = join(dist, route, 'index.html');
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, html);
}
console.log(`Built Yike AI official site: ${routes.length + 1} routes`);
