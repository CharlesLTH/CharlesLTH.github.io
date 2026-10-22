MHXX 资料库：数据整理与静态网站

新版可部署网站位于 games/mhxx/；旧版已移至 games/mhxx_old/，新版不提供旧版入口。
旧目录保留全部资料，继续作为数据提取输入；仅修改首页跳转为相对地址，使归档可独立访问。
上层网站无需修改，原有 mhxx/index.html 链接直接进入新版。
目前已完成武器差异复核，以及怪物、任务、防具、技能、地图采集和调合的本地抽取。
数据库保留来源记录与待核对差异；尚未覆盖旧版全部领域，中文与日文混合字段仍保留原值。
第五阶段已加入前端用静态JSON API v1和浏览器客户端，完整导出核心实体与分页关联。
第六阶段已加入浅色紧凑前端：全局检索、八类详情、素材出处、地图点位及本地收藏。
默认首页为资料导航，保留原站的武器、任务星级、素材、防具、技能、地图及怪物分类，去除新闻。
尚未迁移的猫饭、随从猫等资料暂不提供入口；左上角标识和侧栏入口可随时返回首页。
武器分类支持完整派生树、仅最终、LV1和派生节点等显示模式，直接对照各等级性能并跳转配方。

打开新版前端（当前工作区已完成构建）：
  .venv/bin/python scripts/frontend.py serve --port 8766
  启动后访问 http://127.0.0.1:8766/games/mhxx/
  默认监听0.0.0.0；手机在同一局域网内，将127.0.0.1换成这台电脑的局域网IP即可。
  如只需本机访问，可加--host 127.0.0.1。

修改web/后重新打包：
  .venv/bin/python scripts/frontend.py build
  .venv/bin/python scripts/frontend.py verify
  输出直接替换 games/mhxx/；不要手动编辑生成目录。
  数据输入始终为 games/mhxx_old/，不得改为新版输出目录。

准备环境（已在当前工作区完成）：
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt

获取固定版本的上游数据库（首次需要网络，校验 SHA-256）：
  .venv/bin/python scripts/data.py fetch

离线构建、导出、校验、测试（按顺序执行）：
  .venv/bin/python scripts/data.py build
  .venv/bin/python scripts/data.py check
  .venv/bin/python scripts/data.py export
  .venv/bin/python scripts/data.py verify-export
  .venv/bin/python scripts/frontend.py build
  npm ci --ignore-scripts
  .venv/bin/python -m pytest -q
  npm test

本地预览（无新增Python/npm依赖）：
  .venv/bin/python scripts/data.py serve-data --port 8765 --prefix /games/mhxx/data-api/v1/

预览入口：http://127.0.0.1:8765/games/mhxx/data-api/v1/manifest.json
serve-data运行期间可访问；Ctrl-C停止。完整测试额外使用本机Node执行浏览器客户端的HTTP验证。

查询示例：
  .venv/bin/python scripts/data.py search 贝鲁纳大剑
  .venv/bin/python scripts/data.py weapon 218099 --level 3 --limit 2
  .venv/bin/python scripts/data.py weapon 292565 --level 1 --limit 1
  .venv/bin/python scripts/data.py weapon 234849 --level 1 --limit 1
  .venv/bin/python scripts/data.py monster 1829 --limit 3
  .venv/bin/python scripts/data.py quest 218315 --limit 3
  .venv/bin/python scripts/data.py armor 218352
  .venv/bin/python scripts/data.py skill 183534 --limit 3
  .venv/bin/python scripts/data.py item 219849 --limit 3
  .venv/bin/python scripts/data.py map 2400 --area 1 --rank LR --limit 4
  .venv/bin/python scripts/data.py combine --search 回复药 --limit 5
  .venv/bin/python scripts/data.py combine --search LV2通常弾
  .venv/bin/python scripts/data.py item 189643 --limit 2

输出：
  build/database/mhxx.sqlite       SQLite 审计数据库
  build/database/audit.txt         简要中文报告
  build/database/audit.json        完整覆盖率、来源、待处理记录
  build/database/differences.json  逐条费用/配方差异
  build/database/performance-differences.json 复核身份的性能字段差异
  build/site-data/v1/             完整静态数据包（约100MB，浏览器按详情/分页读取）
  build/site-data/v1/manifest.json API版本、数据版本、来源、目录及覆盖率
  build/site-data/v1/client.mjs    无框架依赖的浏览器查询客户端
  build/site-data/v1/integrity.json 文件SHA-256清单
  games/mhxx/                     可独立托管的资料库前端（含API和地图图片）
  games/mhxx_old/                 旧站归档与HTML提取输入，无新版导航入口

build/ 与 .venv/ 不纳入版本控制；固定版本及哈希保存在 sources/mhgu-db.json。
games/mhxx/ 是供现有静态站点发布的目录，不受 build/ 忽略规则影响。
网站使用main分支根目录发布；更新源码后应重新构建games/mhxx/并随源码一同提交。
完整站点快照可以在没有历史提交的仓库中构建，来源由逐页SHA-256追踪。
保留旧首页地址 /games/mhxx/index/ 到新版首页的跳转；旧资料详情路径暂未逐条映射到新版。
没有入口不等于访问限制：发布后，知道 /games/mhxx_old/ 地址的人仍可直接访问归档。
复核登记在 sources/reviews.json，来源调查记录在 sources/research-notes.json。
构建会重新检查页面哈希、已登记的性能差异以及独立配方证据；输入变化时要求重新复核。
第二阶段结果见 docs/reconciliation.txt；第三阶段说明见 docs/local-domains.txt。
第四阶段（采集与调合）见 docs/acquisition.txt。
第五阶段的接口约定、前端调用与部署路径见 docs/static-api.txt。
第六阶段的功能、交互约束、启动和测试说明见 docs/frontend.txt。
详细设计与表结构见 docs/data-pipeline.txt；最终统计以每次构建的 audit.json 为准。
