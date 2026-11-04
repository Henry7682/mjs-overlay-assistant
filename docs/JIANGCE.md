# 将策本地组合库

在助手设置中打开「配阵设置」，将来源选为「将策本地库」。首次安装与旧配置均默认名将小助手。将策模式使用本机已经确认的武将姓名，离线可用，游戏保持前台。普通或巅峰楚汉选将至少确认两名即可匹配；尚未识别的候选可能还有其他搭配。攻略正文、分享者与座次评分取自[将策组合查询](https://www.jiangce.online/)。卡片中的每个分数只对应写在它旁边的站位。攻略开关、手动重算及战斗收起按钮沿用原设置。

客户端每日首次运行在后台检查数据，跨日再次检查。软件版本和组合库版本独立，当前局采用同一个快照，切回小程序可以继续原有查询。「来源详情」打开该条攻略原文。模式规则与官方单将统计仍以游戏及对应榜单为准。

## 维护端

在项目根目录使用 Python 3.11 锁定环境，运行：

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\sync-jiangce.ps1
~~~

原始 HTML、索引、校验报告和候选库保存在私人 .research/jiangce/YYYYMMDD/。中断后按同一日期续跑；若两次分页对照不一致，保留失败证据，另开独立快照重新采集。手工指定新目录或离线从已归档 HTML 重建：

~~~powershell
.venv\Scripts\python tools\sync_jiangce.py .research\jiangce\retry-01
.venv\Scripts\python tools\build_jiangce.py .research\jiangce\retry-01 .research\jiangce\retry-01\guides.sqlite
.venv\Scripts\python tools\prepare_jiangce.py .research\jiangce\retry-01\guides.sqlite .research\jiangce\channel
~~~

核对 build-report.json 的翻页数、唯一 ID 数、归档详情数、未知姓名与 SHA256。数据变化时发布工具使用现有仓库外 RSA 私钥签署新清单；相同内容重复执行复用版本。请保留 channel 目录，以便与上次签名清单比较。原始 HTML 与表中的稿件署名对应，公开分发只含获准的组合库、签名清单。每次应用正式发布前，把已核对的最新版数据库及其原字节 channel.json、channel.sig 更新到 assets/jiangce，种子库文件名固定为 guides.sqlite。

定时同步可在维护电脑 Windows 任务计划程序设置每日 05:00 运行 powershell.exe，参数 -NoProfile -File "<repo>\tools\sync-jiangce.ps1" -Publish，使用可读取签名密钥、且已为两个远端设置 Git 写入凭据的维护账号，禁止同时运行第二个任务。也可单独运行 tools/publish_jiangce.py .research/jiangce/channel GitHub 或 Gitee。两个站各自使用独立的 jiangce-data 数据分支，常规快进保留旧快照。上传后匿名下载各站 channel.json、channel.sig 及其中对应版本/哈希的 .sqlite，再核对签名、大小、哈希与条数。单站失败只重试该站。软件发行及 main 的更新清单是另一条发布流程。

首批数据库日期 2026-11-04，641 篇。样本「嬴政 × 白起」含 1/4 位 4/5 与反向 2/3 位 5/5。缺少站位、评分或分享者时按原资料显示。将策资料来源及许可与助手自身代码许可分别记录，维护者已确认组合资料可分发。

