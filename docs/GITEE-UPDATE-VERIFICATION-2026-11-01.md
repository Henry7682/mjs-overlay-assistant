# 1.0.2 国内自动更新验收（2026-11-01）

## 结果

国内更新通道已接通。GitHub PR [#10](https://github.com/Henry7682/mjs-overlay-assistant/pull/10) 经保护规则与 CI 合并为 `9b729afb921d0d1d040adca64121f74f66984613`，Gitee main 已同步同一提交。两端在线清单与签名逐字节一致，原始 RSA-3072 公钥验签通过。

本次只添加已验证的镜像 URL、重新签名并更新维护文档；数字版本仍为 1.0.2。GitHub 的 33 份历史附件、Gitee 原有及本次 8 份附件、发行标签和程序内容保持不变。Release 附件中的旧清单继续作为历史快照保留，客户端读取的是 main 根目录的清单。

## 匿名下载

- 8 份 Gitee 附件共448232498字节，未使用浏览器认证；大小、SHA256与分卷合并结果全部匹配。
- Windows PowerShell5.1 使用发行下载库、签名候选清单和 `Gitee` 源，从空缓存下载两个程序分卷，用时118.61秒。
- 合并后程序 payload 为165963795字节；SHA256为 `59d407204ef654ee2478301767eb90a95899dcb018570fec3663ca49eaa35653`。

## 原始启动器端到端测试

环境为 Windows11 x64、Windows PowerShell5.1。三个旧版安装目录独立准备，外层 launch.ps1 和 release/Release.ps1 与其原始发行 ZIP 一致；没有修改启动器来强制 Gitee。

测试包装进程用 .NET WebRequest 的进程内前缀注册，让 GitHub / raw.githubusercontent.com / objects.githubusercontent.com 请求明确失败。Gitee 请求真实联网，线上 main 清单真实读取并验签。没有修改系统代理、DNS或防火墙；这不是对所有无VPN网络的普遍保证。

| 初始版本 | 结果 | 耗时 | 下载状态 |
| --- | --- | --- | --- |
| 1.0.0 | 从Gitee下载并升级到1.0.2 | 164.73秒 | 空缓存，真实分卷下载 |
| 1.0.1 | 升级到1.0.2 | 24.37秒 | 复用上一测试已校验缓存 |
| 1.0.2 | 检查无更高版本，正常启动 | 2.78秒 | 无需下载 |

两次升级均核对新程序路径、OCR就绪握手、current.json提交，以及设置文件和巅峰榜单前后SHA256一致。测试使用独立data、offscreen，关闭小程序查询及诊断采样；结束时只停止精确路径下的测试进程。没有操作游戏或小程序。

## 自动检查及证据

- 33项发行安全、更新、镜像校验相关测试通过。
- PR #10的push CI [41231892319](https://github.com/Henry7682/mjs-overlay-assistant/actions/runs/41231892319) 和PR CI [41231945287](https://github.com/Henry7682/mjs-overlay-assistant/actions/runs/41231945287) 均成功，包含全量测试、Windows构建及冻结自检。
- 原始匿名下载报告、安装前后哈希、升级事件及未修改启动器哈希保存在维护者本地证据目录；私人运行数据不入仓库/分发。
- 国内[发行说明](https://gitee.com/henry7682/mjs-overlay-assistant/releases/tag/v1.0.2)已标明通道接通，同时保留Win10实机尚待验证的说明。

## 持续发布要求与边界

以后发布更高版本时，必须按 [RELEASING](RELEASING.md) 完成资产上传、匿名验证、签名清单PR和两端main同步，再做旧版升级验证。仅创建新Release不会自动生成可用通道。

用户日常使用最外层 launch.cmd 即可自动检查；GitHub不可用时启动器可使用Gitee。下载或启动失败保留/回退旧版；相同版本不会重复更新。正在运行的实例仅唤出设置，源码及直接运行内部EXE的例外不变。下载器的 -Source Gitee 只控制本次下载，助手设置没有持久更新源选择项。

本机成功不代替Win10真实机器、受保护目录、所有网络环境及游戏功能验收。T38及其他独立TODO继续保留。现有1.0.2包不包含后来只合入main、尚未正式发行的源码改动。
