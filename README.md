# 名将浮窗助手

Steam《名将杀》的独立 Windows 悬浮助手：截图识别可见武将，查询本地官方榜单；楚汉争霸可通过微信“名将小助手”公开界面获取阵容参考。

> **当前状态：1.0.0 开源测试版准备中，尚未发布安装包。** 仓库先行开放供代码审查、镜像导入和反馈。源码版本号为目标版本，不代表发布完成。下载器、更新回退和诊断设施仍需验收，详见 [发布状态](docs/RELEASE_STATUS.md)。

## 下载与使用

- [GitHub Releases](https://github.com/Henry7682/mjs-overlay-assistant/releases)：正式公开测试包将发布在这里；目前没有 1.0.0 资产。
- Gitee：由维护者手动导入，实际镜像地址和匿名附件下载尚未核验，暂不提供自动镜像下载承诺。
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
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe tools/restore_models.py
.\.venv\Scripts\python.exe -X utf8 main.py
```

要求 Python 3.11 x64。本仓库尚未完成干净环境安装验收；`requirements.lock.txt` 是当前开发环境版本记录，运行／开发依赖拆分和文件哈希锁定仍在进行。不要使用系统全局 Python 安装这些依赖。

模型不直接放入 Git。`restore_models.py` 会从已安装 RapidOCR 包内寻找并按清单校验模型；如提示缺失，可从自己已有完整便携包的 `_internal/assets/models` 恢复：

```powershell
.\.venv\Scripts\python.exe tools/restore_models.py --from-dir "旧便携目录\_internal\assets\models"
```

独立模型下载包尚待发布；没有匹配模型时暂不能完成源码运行，不要自行替换为不同模型绕过哈希检查。

| 组件 | 用途／下载渠道 | 当前交付情况 |
|---|---|---|
| Python 3.11 x64 | [Python 官方](https://www.python.org/downloads/windows/) | 源码运行需要；未来便携包内置运行时 |
| Python 库 | [PyPI](https://pypi.org/)、[清华镜像](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)、[阿里云镜像](https://mirrors.aliyun.com/pypi/simple/) | 版本见 requirements.lock.txt；哈希锁定与离线包待完成 |
| OCR 模型 | [RapidOCR](https://github.com/RapidAI/RapidOCR) | 清单见 assets/models/manifest.json；独立模型包待发布 |
| 微信 | [微信官方](https://weixin.qq.com/) | 仅配阵需要，用户自行登录并打开小程序 |
| Steam／名将杀 | [Steam 官方](https://store.steampowered.com/) | 用户自行安装游戏，助手不代购或登录 |
| VC++ 运行库 | [微软官方说明](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist) | 运行库检测与安装引导待验收，不从 DLL 下载站补文件 |

需要换 pip 源时，可对上述安装命令添加 `--index-url https://pypi.tuna.tsinghua.edu.cn/simple`，仅本次命令生效，不更改全局设置。未来下载器将统一做版本和哈希验证；现在请勿将未完成的 `download.ps1`／`launch.ps1` 当正式安装入口。

## 反馈与隐私

请描述**实际版本、游戏模式、阶段、具体武将、分辨率／缩放、复现步骤**及哪些功能仍正常。新诊断功能支持预览和导出，但仍在验收；不要把“有日志”当作足以复现所有 Windows 控件延迟。

公开 Issue 不要附原始私人截图。需要原图时，请加入QQ群 **104720192**，联系群主／管理员后私聊发送。助手不自动上传反馈包。普通楚汉查询会把完整游戏 PNG 交给小程序，可能含昵称，小程序可能上传并保留；详情见 [隐私说明](docs/PRIVACY.md)。

开发快照默认启用本地故障画面记录，可在反馈页面关闭。请在运行前阅读首次提示，并在分享任何诊断文件前自行检查。

## 已知问题与开发

- 小程序 UIA 控件读取速度会波动，可能超时；不能保证攻略全部读取完毕，不完整结果会提示。
- 更多皮肤、分辨率、6～12 人巅峰布局、冷启动和持续实战仍有待验收项目。
- 签名更新、下载器、诊断功能和国内镜像未完成正式发布验收。

见 [TODO](TODO.md)、[测试记录](TESTING.md)、[性能调查](PERFORMANCE-2026-10-28.md)、[贡献指南](CONTRIBUTING.md)。仓库 CI 当前仅做 Python 语法检查，不等同 Windows 功能、打包或实战通过。

## 许可与关系说明

本项目自有源码采用 **GPL-3.0-only**，见 [LICENSE](LICENSE)。第三方库、模型、官方榜单、游戏名称及画面裁片分别遵循各自许可和权利声明，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。当前 Qt 许可材料收集仍待补齐，二进制公开发布前必须完成。

本项目是独立助手，不代表游戏官方或名将小助手作者，不宣称合作授权，也不分发小程序配阵数据库。私人实战截图、日志、账户配置和工作区历史不进入公开快照。
