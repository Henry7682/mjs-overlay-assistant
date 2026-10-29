# 本地开发 README

本文面向需要运行、修改和测试源码的开发者。下载使用请从[项目首页](../README.md)开始；发行包安装、缺少 Python 时的下载器方案和离线部署见[安装说明](INSTALL.md)。

## 开始前

使用 Windows 11 x64、Python 3.11 x64。修改前阅读 [AGENTS.md](../AGENTS.md)、[TODO.md](../TODO.md) 和相关 [TESTING.md](../TESTING.md) 历史记录。小程序耗时相关工作还需先阅读[已归档调查](../PERFORMANCE-2026-10-28.md)，避免重复已无稳定收益的实验。

公开仓库只包含经审查的源码和脱敏测试裁片。维护者的完整实战素材不随仓库提供；缺少样本时说明限制，不将缺样本记作验收通过。

## 准备独立环境

安装 [Python 3.11 x64](https://www.python.org/downloads/windows/) 和 [Git](https://git-scm.com/downloads/win)，然后在 PowerShell 运行：

```powershell
git clone https://github.com/Henry7682/mjs-overlay-assistant.git
cd mjs-overlay-assistant
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -Development
.\.venv\Scripts\python.exe -X utf8 main.py
```

也可以下载仓库 ZIP 后解压，从 `setup.ps1` 开始。没有 Python 时，可先使用[下载器 Source 模式](INSTALL.md)准备环境；进入源码目录后再加 `-Development` 安装测试与打包依赖。

`setup.ps1` 在项目内创建 `.venv`。开发依赖采用 `requirements-dev.lock.txt`，仅运行采用 `requirements-runtime.lock.txt`；均锁定版本和哈希。PyPI 失败后依次尝试清华、阿里云单一索引，不修改全局 pip 配置。旧 `requirements.lock.txt` 保留作历史记录。

若 Python 未注册到 `py` 启动器，可显式传入路径：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -Development -Python '你的Python目录\python.exe'
```

模型不直接提交 Git。安装脚本从锁定的 RapidOCR wheel 恢复三份模型并按 `assets/models/manifest.json` 校验；也可以从官方 Release 模型包完整解压后的目录恢复：

```powershell
.\.venv\Scripts\python.exe tools/restore_models.py --from-dir '解压后的模型目录'
```

### 依赖与下载入口

| 组件 | 用途与渠道 |
| --- | --- |
| Python 3.11 x64 | 源码运行需要；[Python 官方](https://www.python.org/downloads/windows/)，便携版内置运行时 |
| Python 库 | [PyPI](https://pypi.org/)、[清华镜像说明](https://mirrors.tuna.tsinghua.edu.cn/help/pypi/)、[阿里云镜像](https://mirrors.aliyun.com/pypi/simple/)；安装脚本逐个尝试，保留锁定哈希 |
| OCR 模型 | [RapidOCR](https://github.com/RapidAI/RapidOCR)；独立模型包见本项目 Release，使用项目清单校验 |
| 微信 | [微信官方](https://weixin.qq.com/)，仅配阵需要；用户自行登录、打开小程序 |
| Steam／游戏 | [Steam 官方](https://store.steampowered.com/)；用户自行安装游戏 |
| VC++ 运行库 | [微软说明](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist)、[x64 安装器](https://aka.ms/vs/17/release/vc_redist.x64.exe)；便携下载器自检失败且检测缺失时下载、验证后提示手动安装 |

## 使用独立测试数据

开发时不要直接共用正在使用的便携版 `data`。可为当前 PowerShell 会话指定独立目录：

```powershell
$env:MJS_ASSISTANT_HOME = Join-Path $PWD '.research\dev-data'
.\.venv\Scripts\python.exe -X utf8 main.py
```

该环境变量影响从当前终端启动的进程。独立数据目录仍可能保存私人画面和日志，不能提交；退出终端不会删除已有数据。

## 代码入口

| 位置 | 职责 |
| --- | --- |
| `main.py`、`mjs_assistant/app.py` | 启动、主界面与流程协调 |
| `capture.py`、`ocr.py`、`recognition.py` | 游戏窗口截图、姓名识别与多帧确认 |
| `entry_detection.py`、`identity_layout.py`、`peak_layout.py` | 模式入口与不同布局 |
| `boards.py`、`storage.py`、`updater.py`、`stats_source.py` | 榜单校验、存储、官方更新与统计来源映射 |
| `mini_*.py`、`provider.py`、`guide_*.py` | 小程序公开界面操作、攻略读取、缓存与面板 |
| `diagnostics.py`、`feedback_ui.py` | 本地故障记录与导出 |
| `release/`、`download.ps1`、`launch.ps1` | 签名清单、下载部署、启动更新与回退 |
| `tests/`、`tools/` | 单元／回放测试和构建维护工具 |

表中 Python 模块默认位于 `mjs_assistant/`。游戏模式与统计来源是两个概念：普通楚汉使用巅峰楚汉榜单，不应因此改变普通楚汉的截图查询流程。

## 测试与证据

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
```

先运行与改动有关的测试，再按影响范围回归。公开 CI 包括锁定依赖安装、测试、构建与冻结离线自检；不会操作游戏或微信。不要在未经用户安排时启动小程序回放脚本，它们可能操作前台窗口。

每次改动分别记录单元测试、截图回放、小程序组件测试、完整实战结果。修改结束及发布前更新 TODO 的版本、证据、待验收场景和通过条件。自动测试通过不关闭仍缺实战证据的条目。

诊断包只读回放入口为 `tools/replay_diagnostics.py`，先通过 `--help` 查看参数。UIA 的实际等待时间只能分析记录，不能通过离线回放保证复现。

## 提交与构建

使用独立分支；PR 说明触发条件、修复后的行为、验证结果与剩余限制。私人截图、日志、运行配置、令牌及第三方配阵数据库不得提交。经授权的脱敏裁片也须人工检查，细则见[贡献指南](../CONTRIBUTING.md)。

本地构建入口为 `build.ps1`。正式分发还需依赖／模型许可收集、公开快照审查、签名、镜像与安装核验，请按[发布维护](RELEASING.md)执行。私钥放在仓库外；不要用本地开发构建覆盖已发布资产或用户正在运行的程序。

仓库根 `README.md` 是 GitHub 用户首页；本文件维护开发步骤。仅修改文档不需要重打便携包，发布时仍应核对链接与公开内容。
