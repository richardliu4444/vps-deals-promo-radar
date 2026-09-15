ILANG
[TYPE:agents][PROJECT:vps-deals-promo-radar][LANG:zh]

::STATE{@PROJECT, name:vps-deals-promo-radar, type:零服务器优惠垂直站, deploy:cloudflare-pages}
::STATE{@DATA, source:公开sitemap/feed/官方优惠页, runtime:纯Python标准库, update:github-actions-cron-6h}

::MODULE{WHAT|title:这个项目是什么}
  一个零成本 零服务器 自动更新的 VPS 优惠聚合站
  scraper.py 抓各家厂商公开优惠页 写 data/offers.json
  build.py 读 offers.json 渲染静态站到 site/
  GitHub Actions 每6小时跑一次 抓+建+commit+部署
  Cloudflare Pages 免费托管 在 pages.dev 上线

::MODULE{CAN_DO|title:允许的动作}
  改 .ilang/site.ilang 加减厂商 改品牌 改渲染规则 重跑 build.py
  改 templates/ 调样式 调布局
  加新的页面模板 build.py 里注册路由
  调 .github/workflows/update.yml 改更新频率

::MODULE{CANNOT|title:绝不许做的}
  ::BOUNDARY{never:编优惠 编价格 编佣金|scope=permanent}
  ::BOUNDARY{never:绕 robots.txt 抓登录后内容|scope=permanent}
  ::BOUNDARY{never:品牌词竞价 cookie 注入|scope=permanent}
  ::BOUNDARY{never:把 site.ilang 改成不读的摆设|scope=permanent}
  ::BOUNDARY{never:引入需要 API key 或收费推理的运行时依赖|scope=permanent}

::MODULE{STRUCTURE|title:仓库结构}
  .ilang/site.ilang     站点规则唯一真源 scraper 和 build 真的读它
  scraper.py            抓数据 写 offers.json
  build.py              渲模板 生成 sitemap robots 到 site/
  templates/            index.html provider.html deal.html compare.html
  data/offers.json      数据集 workflow 每次覆盖
  .github/workflows/    update.yml cron 定时
  site/                 构建产物 部署目录

::MODULE{ILANG|title:协议说明}
  站点规则用 I-Lang 协议描述 见 .ilang/site.ilang
  协议说明 ilang.ai
  拿掉 I-Lang 站照样跑 留着它你接手时不会乱来
