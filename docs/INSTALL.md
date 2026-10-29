# 下载、安装与更新

1.0.0 为公开测试版。GitHub提供完整便携包，Gitee提供下载器和经匿名校验的分卷附件；验证边界见[发布状态](RELEASE_STATUS.md)。

## 最简单：完整便携包

到 [GitHub Releases](https://github.com/Henry7682/mjs-overlay-assistant/releases) 下载 `MjsOverlay-1.0.0-win64.zip`，完整解压到可写的独立目录，双击根目录 `launch.cmd`。不要在ZIP预览中直接运行EXE，也不要将版本目录里的单个EXE拖出来。

便携包内置Python、Qt、OCR和模型。统计不需要微信；配阵需要自行登录微信并打开名将小助手的一键配阵页。第一次启动请阅读本地故障画面说明。程序未购买Windows Authenticode签名证书，可能出现信誉提示；先核对下载来源和哈希，不要关闭系统安全防护。

## PowerShell下载器

在PowerShell中执行以下命令，先保存ZIP，再解压运行本地脚本，不执行远程脚本管道。目录可自行更改。

```powershell
$zip = Join-Path $PWD 'MjsOverlay-downloader.zip'
Invoke-WebRequest -UseBasicParsing 'https://github.com/Henry7682/mjs-overlay-assistant/releases/download/v1.0.0/MjsOverlay-1.0.0-downloader.zip' -OutFile $zip
Expand-Archive -LiteralPath $zip -DestinationPath '.\MjsDownloader'
powershell -NoProfile -ExecutionPolicy Bypass -File .\MjsDownloader\download.ps1 -Mode Portable -Source Auto -Destination '.\MjsOverlay'
```

命令提示符中也可运行：

```bat
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing 'https://github.com/Henry7682/mjs-overlay-assistant/releases/download/v1.0.0/MjsOverlay-1.0.0-downloader.zip' -OutFile 'MjsOverlay-downloader.zip'; Expand-Archive -LiteralPath 'MjsOverlay-downloader.zip' -DestinationPath 'MjsDownloader'"
MjsDownloader\download.cmd -Mode Portable -Source Auto -Destination "%CD%\MjsOverlay"
```

GitHub下载较慢时，改从Gitee取得同一下载器，并固定国内资产源：

```powershell
Invoke-WebRequest -UseBasicParsing 'https://gitee.com/henry7682/mjs-overlay-assistant/releases/download/v1.0.0/MjsOverlay-1.0.0-downloader.zip' -OutFile '.\MjsOverlay-downloader.zip'
Expand-Archive -LiteralPath '.\MjsOverlay-downloader.zip' -DestinationPath '.\MjsDownloader'
powershell -NoProfile -ExecutionPolicy Bypass -File .\MjsDownloader\download.ps1 -Source Gitee -Destination '.\MjsOverlay'
```

`ExecutionPolicy Bypass`仅对本次子进程生效，不修改系统策略。首次下载器的可信性来自你核对的仓库／Release来源；后续清单签名不能证明最初引导脚本未被篡改。

| 参数 | 用途 |
|---|---|
| `-Mode Portable` | 默认：部署包含全部运行组件的便携版 |
| `-Mode Source` | 下载对应源码、准备Python3.11 x64独立环境及模型 |
| `-Source Auto` | 默认：尝试经签名清单登记的可用源 |
| `-Source GitHub`／`Gitee` | 固定助手资产来源；厂商安装器仍使用官方渠道 |
| `-Destination '路径'` | 可写、独立目录；保留已存在配置，不降级 |
| `-OfflineDirectory '路径'` | 从本地清单、完整包或分卷读取，不联网取助手资产 |
| `-CheckOnly` | 仅报告系统／运行库及程序状态，不安装 |

Gitee镜像入口：[发行页](https://gitee.com/henry7682/mjs-overlay-assistant/releases)。下载器ZIP可从该页手动保存，然后运行相同命令。镜像地址均经过匿名校验；若以后页面变为登录页／验证码，下载器拒绝将其作为文件使用。QQ群104720192仅为人工备用，不提供自动群文件接口。

## 源码与离线安装

有Python3.11 x64时，下载仓库ZIP并解压，运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1`，然后双击 `start.cmd`。开发构建加 `-Development`。不要使用系统全局pip安装依赖。

下载器的Source模式若找不到兼容Python，会验证官方Python安装器哈希和PSF发布者签名，然后按用户范围安装，不改系统PATH或替换其他Python。Steam、游戏和微信由用户自行安装登录。

离线目录需包含 `release.json`、`release.sig` 以及清单对应资产：Portable需要payload；Source需要source、models、offline-wheels；无Python时还需官方Python安装器。完整ZIP或全部`.partNN`均可，下载器自动合并、逐卷及整包校验，不需要7-Zip。清单可从发行附件或Gitee仓库根目录的[release.json](https://gitee.com/henry7682/mjs-overlay-assistant/raw/main/release.json)及[release.sig](https://gitee.com/henry7682/mjs-overlay-assistant/raw/main/release.sig)保存；两者须来自同一版。分卷必须来自同一版；不要自行拼接不同版本。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\MjsDownloader\download.ps1 -Mode Portable -OfflineDirectory '.\MjsOffline' -Destination '.\MjsOverlay'
```

## 更新、数据与回退

每次从根目录 `launch.cmd` 启动，先检查签名清单（总预算8秒）。新版下载可按 **S** 跳过；断网或失败时启动原版。自动下载总预算180秒，无进度15秒尝试其他可用源。新版须在60秒内完成界面及OCR初始化握手，否则回退旧程序和配置／榜单，并暂停自动重试该失败版本。

目录结构：`versions\版本号`保存程序，根目录`data`保存配置／榜单／日志；`current.json`指向当前版本，`update-backups`保留升级前配置和榜单。不要覆盖或删除`data`。再次启动正在运行的同目录助手只打开设置，不中断当前查询。

旧0.3.x数据通过设置内“导入旧版data目录”迁移，先自动备份，再校验模式和格式；不要手工把旧运行文件混入新版本目录。需要回退时关闭助手、保留data副本，使用上一个完整便携包或维护者提供的恢复步骤。不要修改签名清单绕过失败检查。

软件更新与官方榜单更新独立。榜单启动检查、运行期间每24小时复查；网络后台获取，繁忙时延后大图OCR。错误或有疑点的新榜单进入复核区，当前有效数据继续使用。源码运行仅提示发布信息，不自动覆盖Git工作区。
