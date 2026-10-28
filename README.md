# 名将浮窗助手

Steam《名将杀》的独立 Windows 悬浮助手：截图识别可见武将，查询本地官方榜单；楚汉争霸可通过微信“名将小助手”公开界面获取阵容参考。

> **1.0.0 公开测试版，用于招募测试与反馈。** 当前发布资产仍在最后的国内镜像验证阶段，GitHub Release尚为草稿；可用下载渠道以公开发行页为准，详见[发布状态](docs/RELEASE_STATUS.md)。已知识别布局和小程序延迟问题会持续跟踪，不承诺所有环境都已实战验收。

## 下载与使用

- [GitHub Releases](https://github.com/Henry7682/mjs-overlay-assistant/releases)：正式公开测试包将发布在这里；目前没有 1.0.0 资产。
- [Gitee 国内源码镜像](https://gitee.com/henry7682/mjs-overlay-assistant)：仓库已建立，匿名源码访问已验证；分卷下载附件仍在准备，当前不能替代完整安装包。
- [使用说明](docs/USAGE.md)：模式、统计来源、小程序准备、战斗攻略及快捷键。
- [反馈问题](https://github.com/Henry7682/mjs-overlay-assistant/issues/new/choose)：公开问题表单；QQ群 **104720192**。

首发目标为 **Windows 11 x64、Steam 版、窗口化或无边框**。推荐显示环境为 **2560×1440、150% 缩放**。Windows 10、其他分辨率和部分布局待社区验证；独占全屏不在首发验收范围。

数据浮窗查询本地榜单，离线可用。攻略浮窗额外依赖已登录的微信和已打开的“名将小助手 → 一键配阵”；查询可能切换前台窗口。助手不在游戏中禁将、选将、锁将或出牌。

| 模式 | 数据浮窗 | 阵容参考 |
|---|---|---|
| 明刀暗箭·八人身份 | 支持 | 不提供 |
| 排位·楚汉争霸 | 使用巅峰楚汉统计，明确显示来源 | 小程序截图查询 |
| 巅峰·楚汉争霸 | 支持 | 小程序公开选将页查询、局内缓存 |
| 巅峰·双龙争鼎 | 支持 | 不提供 |

默认重新配阵 **Ctrl+Alt+P**，展开／收起攻略 **Ctrl+Alt+D**，取消 **Ctrl+Alt+X**。升级时保留旧配置和用户自定义按键；冲突时在设置中修改。统计周期始终按实际榜单显示，不把旧数据标为当期。

## 源码下载与运行（开发者）

可使用 Git，或点击本页 **Code → Download ZIP**，下载后完整解压：

```powershell
git clone https://github.com/Henry7682/mjs-overlay-assistant.git
cd mjs-overlay-assistant
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
.\.venv\Scripts\python.exe -X utf8 main.py
```

要求 Python 3.11 x64。`setup.ps1` 在项目内建立 `.venv`，按 `requirements-runtime.lock.txt` 安装经过哈希锁定的wheel；官方PyPI失败后逐个尝试清华、阿里云，不修改全局pip配置。开发测试使用 `-Development`，安装 `requirements-dev.lock.txt`。旧 `requirements.lock.txt` 仅为历史记录。干净Windows验证结果见发布状态。

模型不直接放入 Git。`restore_models.py` 会从已安装 RapidOCR 包内寻找并按清单校验模型；如提示缺失，可从自己已有完整便携包的 `_internal/assets/models` 恢复：

```powershell
.\.venv\Scripts\python.exe tools/restore_models.py --from-dir "旧便携目录\_internal\assets\models"
```

锁定的 RapidOCR wheel 已包含三份匹配模型，安装脚本会恢复并校验；另准备独立模型包和离线wheel包。缺失或校验不符时停止，不替换为不同模型。

| 组件 | 用途／下载渠道 | 当前交付情况 |
|---|---|---|
| Python 3.11 x64 | [Python 官方](https://www.python.org/downloads/windows/) | 源码运行需要；未来便携包内置运行时 |
| Python 库 | [PyPI](https://pypi.org/)、[清华镜像](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)、[阿里云镜像](https://mirrors.aliyun.com/pypi/simple/) | 运行35项／开发45项，版本和哈希见两份lock文件；便携版内置 |
| OCR 模型 | [RapidOCR](https://github.com/RapidAI/RapidOCR) | 清单见 assets/models/manifest.json；独立模型包待发布 |
| 微信 | [微信官方](https://weixin.qq.com/) | 仅配阵需要，用户自行登录并打开小程序 |
| Steam／名将杀 | [Steam 官方](https://store.steampowered.com/) | 用户自行安装游戏，助手不代购或登录 |
| VC++ 运行库 | [微软官方说明](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist)、[x64安装器](https://aka.ms/vs/17/release/vc_redist.x64.exe) | 下载器检测；便携自检失败且运行库缺失时下载并验证微软签名，用户自行安装 |

下载器、命令提示符／PowerShell完整命令、离线安装和更新回退步骤见 [下载安装](docs/INSTALL.md)。公开资产就绪前，在线安装命令不能完成安装；不要把开发快照当作正式发行包。

## 反馈与隐私

请描述**实际版本、游戏模式、阶段、具体武将、分辨率／缩放、复现步骤**及哪些功能仍正常。新诊断功能支持预览和导出，但仍在验收；不要把“有日志”当作足以复现所有 Windows 控件延迟。

公开 Issue 不要附原始私人截图。需要原图时，请加入QQ群 **104720192**，联系群主／管理员后私聊发送。助手不自动上传反馈包。普通楚汉查询会把完整游戏 PNG 交给小程序，可能含昵称，小程序可能上传并保留；详情见 [隐私说明](docs/PRIVACY.md)。

开发快照默认启用本地故障画面记录，可在反馈页面关闭。请在运行前阅读首次提示，并在分享任何诊断文件前自行检查。

## 已知问题与开发

- 小程序 UIA 控件读取速度会波动，可能超时；不能保证攻略全部读取完毕，不完整结果会提示。
- 更多皮肤、分辨率、6～12 人巅峰布局、冷启动和持续实战仍有待验收项目。
- 签名更新、下载器、诊断功能和国内镜像未完成正式发布验收。

见 [TODO](TODO.md)、[测试记录](TESTING.md)、[性能调查](PERFORMANCE-2026-10-28.md)、[贡献指南](CONTRIBUTING.md)。CI包含语法检查、Windows哈希依赖安装、单元／回放测试、构建及冻结程序离线自检；实际通过状态以Actions与发布记录为准，CI不操作游戏或小程序，不代替实战。

## 许可与关系说明

本项目自有源码采用 **GPL-3.0-only**，见 [LICENSE](LICENSE)。第三方库、模型、官方榜单、游戏名称及画面裁片分别遵循各自许可和权利声明，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。Qt及其第三方通知、动态库替换和源码取得说明随包保留。

本项目是独立助手，不代表游戏官方或名将小助手作者，不宣称合作授权，也不分发小程序配阵数据库。私人实战截图、日志、账户配置和工作区历史不进入公开快照。
