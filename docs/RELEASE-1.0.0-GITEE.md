# 名将浮窗助手 1.0.0 · 公开测试版

**首个开源测试版本，欢迎玩家参与测试，也欢迎开发者共同完善。**

原“名将统计助手”正式更名为“名将浮窗助手”。本版整合四模式武将统计、二二配阵攻略、下载更新与诊断反馈。统计可离线使用；攻略需配合微信“名将小助手”。

适用环境：**Windows 11 x64 · Steam《名将杀》· 窗口化／无边框**。推荐 **2560×1440、150% 缩放**；其他分辨率、Windows 10 和更多布局仍待社区验证。

## 国内下载与启动

**普通用户下载本页附件：[MjsOverlay-1.0.0-downloader.zip](https://gitee.com/henry7682/mjs-overlay-assistant/releases/download/v1.0.0/MjsOverlay-1.0.0-downloader.zip)**。

1. 完整解压下载器。
2. 双击 `download.cmd`，或在下载器目录用下方命令指定 Gitee。
3. 等待下载、自动合并分卷和校验完成。
4. 双击目标目录中的 **`launch.cmd`** 启动助手。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\download.ps1 -Mode Portable -Source Gitee -Destination .\MjsOverlay
```

安装后运行 `MjsOverlay\launch.cmd`。便携版已内置 Python、Qt、OCR 库与模型，无需逐个安装。

### 本页附件说明

| 附件 | 用途 |
| --- | --- |
| `MjsOverlay-1.0.0-downloader.zip` | 普通用户推荐；负责下载、合并、校验和安装 |
| `MjsOverlay-1.0.0-payload.zip.part01`／`part02` | 便携程序的两份分卷，由下载器使用 |
| `MjsOverlay-1.0.0-source.zip` | 源码包，供开发／调试 |
| `MjsOverlay-1.0.0-models.zip` | 独立 OCR 模型；便携版已内置 |
| `MjsOverlay-1.0.0-offline-wheels-win64.zip.part01`～`part03` | 源码离线依赖的三份分卷 |

**不要单独解压 `.partNN`，不要混用不同版本的分卷。** 下载器会自动合并；本页没有独立的完整 win64 ZIP，需要完整包可前往 [GitHub Release](https://github.com/Henry7682/mjs-overlay-assistant/releases/tag/v1.0.0)。

离线部署还需同版 [release.json](https://gitee.com/henry7682/mjs-overlay-assistant/raw/main/release.json) 与 [release.sig](https://gitee.com/henry7682/mjs-overlay-assistant/raw/main/release.sig)。这两个 main 链接跟随最新发行，保存时务必核对清单版本；安装旧版请从 [GitHub 的 v1.0.0 附件](https://github.com/Henry7682/mjs-overlay-assistant/releases/tag/v1.0.0)取得对应清单。具体资产组合见[国内安装说明](https://gitee.com/henry7682/mjs-overlay-assistant/blob/main/docs/INSTALL.md)。

## 本版重点

### 武将统计：四模式可用

支持 **明刀暗箭、排位楚汉争霸、巅峰楚汉争霸、双龙争鼎** 的选将与战斗统计，以及偃师傀儡候选。姓名旁显示胜率、胜率排名、出场排名，顶部显示模式和真实统计周期。

- 普通楚汉使用**巅峰楚汉榜单**，浮窗明确标注来源。
- 强力单将带有“强势”标记；缺少数据时不填零、不补造出场率。
- 持续自动识别入口，也可手动固定模式；支持校准、姓名纠正和鼠标穿透标注。

### 二二攻略：查询、缓存与战斗面板

两种楚汉模式通过名将小助手**公开界面**获取阵容参考，保留原始座次与说明。进入战斗后，攻略收起为可拖动按钮，可展开查看己方／敌方参考。

- 普通楚汉使用截图查询；巅峰楚汉输入本地已识别姓名，并在禁将结束后筛选本局缓存。
- 普通自动操作预算 **15 秒**，巅峰 **40 秒**；超时或列表未读全时尽量保留已有攻略，标明不完整。
- 攻略可单独关闭，小程序查询失败不应阻止本地武将统计。

### 部署、更新与反馈

- 便携包内置运行组件；下载器提供 GitHub／Gitee、源码与离线安装入口。
- 从 `launch.cmd` 启动检查签名更新清单，更新失败保留可用旧版；配置与榜单独立保存。
- 官方榜单启动检查、运行期间每 24 小时复查；有疑点的新数据进入待复核区。
- 提供本地故障记录、诊断包预览／遮挡和导出，便于反馈与排查。

## 首次使用与旧版迁移

1. **只看统计**：启动助手，保持自动模式或选择当前玩法，即可进入游戏；无需微信。
2. **需要配阵**：自行登录微信，打开“名将小助手 → 一键配阵”，准备好“按强度／位置不限”页面。查询会切换前台窗口，尽量让小程序保持前台直到提交完成。
3. **从 0.3.x 升级**：在新版本设置中使用“导入旧版 data 目录”，迁移前会备份。保留旧版目录和数据，不要把旧 EXE／DLL 混入新包。

新配置默认开启攻略、小程序查询和自动查询；升级保留已有开关、快捷键与校准。默认快捷键：

| 操作 | 快捷键 |
| --- | --- |
| 重新配阵；战斗中重试敌方查询 | `Ctrl+Alt+P` |
| 展开／收起攻略 | `Ctrl+Alt+D` |
| 取消当前自动操作 | `Ctrl+Alt+X` |

## 测试版已知限制

- **小程序控件读取耗时仍会波动**，可能页面未就绪、超时或只读到部分攻略；本版没有彻底解决此问题。
- 部分皮肤、布局、多分辨率／DPI、冷启动与连续查询仍待实战验收；独占全屏不在当前支持验收范围。
- 榜单更新取决于官方发布与本地校验。尚无新一期可用时继续使用旧榜，显示真实周期。
- 已完成 **309 项自动测试、Windows CI、Gitee 便携／源码在线安装验证**。这些结果不等于所有环境都已实战通过。

## 测试反馈与隐私

欢迎反馈识别错误、查询中断、安装更新问题，也欢迎提交成功运行的环境与场景。请提供：**版本、模式／阶段、具体武将、分辨率／缩放、复现步骤、发生时间和诊断编号**。

- [GitHub 问题表单](https://github.com/Henry7682/mjs-overlay-assistant/issues/new/choose)
- **QQ群：104720192**
- 优先附助手导出的**默认无图公开反馈包**。需要原始截图时，联系群主／管理员后**私聊发送**，不要发到公开 Issue。

默认开启本地故障画面记录，首次运行会说明，可在反馈页面关闭和清理；助手不会自动上传诊断包。普通楚汉配阵会将完整游戏截图交给小程序，可能包含昵称，小程序可能上传或保留副本。

本助手不在游戏中禁将、选将、锁将或出牌；不代表游戏官方或名将小助手作者。自有源码采用 GPL-3.0-only，第三方许可随包保留。程序未作 Windows Authenticode 签名；发行清单签名用于完整性校验，不等同于系统信誉认证。

[使用手册](https://gitee.com/henry7682/mjs-overlay-assistant/blob/main/docs/USAGE.md) · [隐私说明](https://gitee.com/henry7682/mjs-overlay-assistant/blob/main/docs/PRIVACY.md) · [待验收清单](https://github.com/Henry7682/mjs-overlay-assistant/blob/main/TODO.md) · [参与开发](https://github.com/Henry7682/mjs-overlay-assistant/blob/main/docs/DEVELOPMENT.md)
