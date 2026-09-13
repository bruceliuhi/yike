import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)));
const dist = join(root, 'dist');
const site = 'https://www.tuokexing.net';
const routes = [
  { route: 'products/workbench', key: 'products-workbench' },
  { route: 'products/crm', key: 'products-crm' },
  { route: 'features', key: 'features' },
  { route: 'download', key: 'download' },
  { route: 'roadmap', key: 'roadmap' },
  { route: 'contact', key: 'contact' },
  { route: 'faq', key: 'faq' },
];
const pages = {
  home: {
    path: '/',
    title: '意客 AI｜全网智能获客与证据化商机工作台',
    description: '意客 AI 从已授权平台与可访问公开来源发现正在发生的需求，整理成带原文证据、匹配理由和下一步动作的销售机会。',
    heading: '客户还没开口，意客 AI 先发现。',
  },
  'products-workbench': {
    path: '/products/workbench/',
    title: '商机工作台｜意客 AI 全网智能获客',
    description: '商机工作台围绕业务画像研究已授权平台与公开来源，保存原文证据、匹配理由、人工复核和跟进动作。',
    heading: '商机工作台：从公开信号到可跟进机会。',
  },
  'products-crm': {
    path: '/products/crm/',
    title: '客户情报 CRM｜意客 AI 销售协作',
    description: '客户情报 CRM 组织公司、联系人、商机、活动、客户情报和 AI 草稿，让销售团队围绕同一份事实协作。',
    heading: '客户情报 CRM：让每一次销售跟进都有下一步。',
  },
  features: {
    path: '/features/',
    title: '能力全景｜意客 AI 获客、证据与跟进',
    description: '查看意客 AI 的业务画像、多平台研究、证据复核、监控、触达、客户情报和企业交付能力，以及各能力状态。',
    heading: '从信息捕获到客户跟进，一条完整的增长链。',
  },
  download: {
    path: '/download/',
    title: '下载与试用｜意客 AI 商机工作台与客户情报 CRM',
    description: '了解意客 AI 商机工作台桌面客户端和客户情报 CRM 网页产品的体验、授权、安装与试用方式。',
    heading: '先用真实业务，判断它值不值得留下。',
  },
  roadmap: {
    path: '/roadmap/',
    title: '产品路线｜意客 AI 证据化获客工作系统',
    description: '查看意客 AI 当前可体验能力、企业方案和持续演进方向；已提供、可开通与规划中能力分别说明。',
    heading: '从一条证据链开始，让每一次跟进都有依据。',
  },
  contact: {
    path: '/contact/',
    title: '预约演示与试用｜意客 AI',
    description: '带着真实业务预约意客 AI 演示，了解从业务画像、公开来源研究到机会证据和跟进草稿的完整链路。',
    heading: '带着真实业务来，看一条机会如何被推进。',
  },
  faq: {
    path: '/faq/',
    title: '常见问题｜意客 AI 平台、数据边界与试用方式',
    description: '了解意客 AI 的产品定义、平台范围、公开信息边界、人工确认、数据权限和 7 天试用方式。',
    heading: '关于意客 AI，你需要先知道的事。',
  },
};

const fallback = {
  home: `<section class="seo-fallback"><p>意客 AI · 全网智能获客</p><h1>客户还没开口，意客 AI 先发现。</h1><p>意客 AI 从已授权平台与可访问公开来源发现正在发生的需求，整理成带原文证据、匹配理由和下一步动作的销售机会。</p><p><a href="/products/workbench/">了解商机工作台</a>　<a href="/products/crm/">了解客户情报 CRM</a>　<a href="/contact/">申请试用</a></p><h2>核心能力</h2><ul><li>业务画像与搜索条件</li><li>小红书、抖音、B站、知乎等授权平台与公开网页研究</li><li>原文证据、匹配理由、人工复核</li><li>评论与私信草稿、回复记录和客户情报 CRM</li></ul></section>`,
  'products-workbench': `<section class="seo-fallback"><p>意客 AI · 商机工作台</p><h1>商机工作台：从公开信号到可跟进机会。</h1><p>围绕业务画像研究已授权平台与可访问公开来源，保存原文证据、匹配理由、人工复核和跟进动作。</p><h2>适合需要主动获客的企业销售团队</h2><p>支持业务画像、搜索条件、线索采集、监控任务、机会库、原文证据、联系准备和跟进记录。</p></section>`,
  'products-crm': `<section class="seo-fallback"><p>意客 AI · 客户情报 CRM</p><h1>客户情报 CRM：让每一次销售跟进都有下一步。</h1><p>组织公司、联系人、商机、活动、客户情报和 AI 草稿，让销售团队围绕同一份事实协作。</p><h2>从线索进入，到客户持续经营</h2><p>支持线索导入、联系人、销售管道、客户情报证据账本、活动、待办和审计记录。</p></section>`,
  features: `<section class="seo-fallback"><p>意客 AI · 能力全景</p><h1>从信息捕获到客户跟进，一条完整的增长链。</h1><p>业务画像、多平台研究、证据复核、监控、触达、客户情报和企业交付能力按状态说明。</p><h2>AI 负责理解和推进，人负责确认和决策。</h2></section>`,
  download: `<section class="seo-fallback"><p>意客 AI · 下载与试用</p><h1>先用真实业务，判断它值不值得留下。</h1><p>商机工作台提供桌面客户端体验，客户情报 CRM 提供网页产品体验；安装包和授权按版本与连接状态提供。</p></section>`,
  roadmap: `<section class="seo-fallback"><p>意客 AI · 产品路线</p><h1>从一条证据链开始，让每一次跟进都有依据。</h1><p>当前可体验能力、企业方案和持续演进方向分别说明，不把规划能力当成现有交付。</p></section>`,
  contact: `<section class="seo-fallback"><p>意客 AI · 预约演示</p><h1>带着真实业务来，看一条机会如何被推进。</h1><p>填写业务场景或拨打 150 1156 9988，了解从业务画像、公开来源研究到机会证据和跟进草稿的完整链路。</p></section>`,
  faq: `<section class="seo-fallback"><p>意客 AI · 常见问题</p><h1>关于意客 AI，你需要先知道的事。</h1><h2>意客 AI 是什么？</h2><p>意客 AI 是面向企业销售团队的客户情报与商机工作台，用于发现公开需求信号、复核机会证据并准备下一步跟进。</p><h2>支持哪些平台？</h2><p>按授权和连接状态支持小红书、抖音、B站、知乎等平台，并可研究公开网页与行业社区。实际可用范围以账号授权、连接状态和项目配置为准。</p><h2>“全网”具体指什么？</h2><p>这里的全网，指已授权的平台与系统当前可访问的公开来源，不代表绕过登录、权限或平台限制，也不承诺无限制覆盖所有网站。</p><h2>会自动发送消息吗？</h2><p>评论和私信先生成草稿，外部触达在发送前由人确认。系统会记录发送、回复和下一步，便于团队复核与协作。</p><h2>试用能拿到什么？</h2><p>围绕一个真实业务场景完成首轮研究，交付可复核的机会记录、原文证据和带上下文的跟进草稿；具体范围按授权和版本确认。</p></section>`,
};

function jsonLd(key) {
  const page = pages[key];
  const organization = { '@type': 'Organization', '@id': `${site}/#organization`, name: '意客 AI', url: site, logo: `${site}/brand/yike-logo-mark.png` };
  const graph = [organization, { '@type': 'WebSite', '@id': `${site}/#website`, url: site, name: '意客 AI', publisher: { '@id': `${site}/#organization` }, inLanguage: 'zh-CN' }, { '@type': 'WebPage', '@id': `${site}${page.path}#webpage`, url: `${site}${page.path}`, name: page.title, description: page.description, isPartOf: { '@id': `${site}/#website` }, about: { '@id': `${site}/#organization` }, inLanguage: 'zh-CN' }];
  if (key === 'products-workbench' || key === 'products-crm') graph.push({ '@type': 'SoftwareApplication', name: key === 'products-workbench' ? '意客 AI 商机工作台' : '意客 AI 客户情报 CRM', applicationCategory: 'BusinessApplication', operatingSystem: key === 'products-workbench' ? 'macOS, Windows' : 'Web', url: `${site}${page.path}`, publisher: { '@id': `${site}/#organization` }, description: page.description });
  if (key === 'faq') graph.push({ '@type': 'FAQPage', mainEntity: [{ '@type': 'Question', name: '意客 AI 是什么？', acceptedAnswer: { '@type': 'Answer', text: '意客 AI 是面向企业销售团队的客户情报与商机工作台，用于发现公开需求信号、复核机会证据并准备下一步跟进。' } }, { '@type': 'Question', name: '支持哪些平台？', acceptedAnswer: { '@type': 'Answer', text: '按授权和连接状态支持小红书、抖音、B站、知乎等平台，并可研究公开网页与行业社区。实际可用范围以账号授权、连接状态和项目配置为准。' } }, { '@type': 'Question', name: '“全网”具体指什么？', acceptedAnswer: { '@type': 'Answer', text: '这里的全网，指已授权的平台与系统当前可访问的公开来源，不代表绕过登录、权限或平台限制，也不承诺无限制覆盖所有网站。' } }, { '@type': 'Question', name: '会自动发送消息吗？', acceptedAnswer: { '@type': 'Answer', text: '评论和私信先生成草稿，外部触达在发送前由人确认。系统会记录发送、回复和下一步，便于团队复核与协作。' } }, { '@type': 'Question', name: '7 天试用能拿到什么？', acceptedAnswer: { '@type': 'Answer', text: '围绕一个真实业务场景完成首轮研究，交付可复核的机会记录、原文证据和带上下文的跟进草稿；具体范围按授权和版本确认。' } }] });
  if (key !== 'home') graph.push({ '@type': 'BreadcrumbList', itemListElement: [{ '@type': 'ListItem', position: 1, name: '首页', item: site + '/' }, { '@type': 'ListItem', position: 2, name: page.title.split('｜')[0], item: site + page.path }] });
  return `<script type="application/ld+json">${JSON.stringify({ '@context': 'https://schema.org', '@graph': graph })}</script>`;
}

const base = await readFile(join(root, 'index.html'), 'utf8');
await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });
await cp(join(root, 'src'), join(dist, 'src'), { recursive: true });
await cp(join(root, 'public'), join(dist), { recursive: true });

function renderHtml(key) {
  const page = pages[key];
  const canonical = `${site}${page.path}`;
  const head = `\n    <link rel="canonical" href="${canonical}" />\n    <meta property="og:type" content="website" />\n    <meta property="og:url" content="${canonical}" />\n    <meta property="og:site_name" content="意客 AI" />\n    <meta property="og:locale" content="zh_CN" />\n    <meta name="twitter:card" content="summary_large_image" />\n    <meta name="twitter:title" content="${page.title}" />\n    <meta name="twitter:description" content="${page.description}" />\n    <meta name="twitter:image" content="${site}/product-screenshots/workbench-navigation.png" />\n    ${jsonLd(key)}`;
  return base
    .replace(/<title>[\s\S]*?<\/title>/, `<title>${page.title}</title>`)
    .replace(/<meta name="description" content="[^"]*" \/>/, `<meta name="description" content="${page.description}" />`)
    .replace(/<meta property="og:title" content="[^"]*" \/>/, `<meta property="og:title" content="${page.title}" />`)
    .replace(/<meta property="og:description" content="[^"]*" \/>/, `<meta property="og:description" content="${page.description}" />`)
    .replace(/<meta property="og:image" content="[^"]*" \/>/, `<meta property="og:image" content="${site}/product-screenshots/workbench-navigation.png" />`)
    .replace('</head>', `${head}\n  </head>`)
    .replace('<div id="app"></div>', `<div id="app">${fallback[key]}</div>`)
    .replace('data-page="home"', `data-page="${key}"`);
}

await writeFile(join(dist, 'index.html'), renderHtml('home'));
for (const item of routes) {
  const target = join(dist, item.route, 'index.html');
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, renderHtml(item.key));
}
console.log(`Built Yike AI official site: ${routes.length + 1} routes`);
