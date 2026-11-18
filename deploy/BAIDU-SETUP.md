# 百度统计站点准备与验收

当前已实现访客同意后加载百度统计脚本、Vue 路由手动 pageview 和一方 PV/UV 采集。2026-11-18 已安装真实跟踪 ID，健康及公开配置检查通过；用户在 https://kongqi.xyz/ 同意统计、浏览首页和文章后，明确确认百度后台已有访问记录或 PV/UV，真实域名采集验收通过。

排查历史：早期本机与服务器获取该 ID 的 hm.js 均为 HTTP 200、0 字节；用户确认地址正确且站点刚创建。2026-11-18T11:49:57Z 脚本已返回 HTTP 200、application/javascript、解压后 29896 字节。用户本机刷新后仍无数据，随后真实域名访问出现记录；没有据此认定本机无数据的唯一原因。当前验收结论以上方最新结果为准。

## 创建站点与获取 ID

1. 打开[百度统计](https://tongji.baidu.com/)，登录或按页面要求开通账号。
2. 进入“管理 → 网站列表 → 新增网站”，网站域名填 kongqi.xyz，网站首页填 https://kongqi.xyz，网站名称可填 Kongqi 博客。
3. 创建后打开“获取代码”，找到代码中的 `https://hm.baidu.com/hm.js?`，保存问号后面的 32 位小写字母/数字跟踪 ID。不要使用报告网址中的纯数字 siteId；不要复制整个 script 标签作为配置值。
4. 该 ID 是网页公开的跟踪标识，可以在协作会话提供。无需提供百度账号密码、Cookie、API Access Token 或授权码。

官方步骤：[创建站点](https://tongji.baidu.com/holmes/Tongji/使用指南/账户管理/站点管理/如何创建站点)、[获取代码](https://tongji.baidu.com/web/help/article?id=170)。以账号实际展示的产品权限和页面为准。

若“首页代码状态”为“无法完成检查”，[官方说明](https://tongji.baidu.com/web/help/article?id=185&type=0)指百度服务器未能正常访问该网站，应转为手动检查实际请求。它不同于“代码安装错误”。新建或变更设置一般约二十分钟生效，见[设置说明](https://tongji.baidu.com/web/help/article?id=244&type=0)；不能仅凭等待时间认定脚本和报告已成功。

## 安装与单页应用设置

取得真实 ID 后，在项目根目录运行 `backend/.venv/Scripts/python.exe deploy/configure_baidu.py <32位跟踪ID>`。工具仅修改服务器 BAIDU_HM_ID，保留其他凭据，检查服务健康及公开配置；失败恢复原环境文件。不向百度伪造浏览或自动制造访问数据。

项目通过 `_setAutoPageview(false)` 禁用初始自动 PV，然后按 Vue 路由发送 `_trackPageview`。百度后台若有“SPA 页面追踪”自动选项，联调时不要同时开启另一套自动路由采集，以免与当前手动上报重复。参见[百度单页应用说明](https://tongji.baidu.com/web/help/article?id=324&type=0)。

## 真实验收

用户同意匿名统计后，在浏览器访问首页、文章详情，再切换路由；核对 hm.js 已加载、百度采集请求已发出。接着在自己的百度后台核对站点、时间范围、受访页面、PV/UV 或实时访客记录。脚本返回 200 和一方后台计数不能证明百度报告已收到数据；不同统计口径也不要求数值完全相等。

本机 127.0.0.1 的联调只证明本机环境的对应链路，不直接代表 kongqi.xyz 正式域名数据已被正确归集。真实域名的报告仍需单独验收；ICP 及正式公网发布保持原先未完成状态，不以统计配置代替。

可通过 `backend/.venv/Scripts/python.exe deploy/remote.py deploy/verify-baidu.sh` 从服务器检查公开配置和脚本响应。该检查不向百度发送页面浏览事件，也不能替代用户在浏览器和统计后台的实际验收。
