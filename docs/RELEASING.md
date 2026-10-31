# 发布维护

只有通过发布阻断项后才公开普通Release；已知UIA延迟和缺少实战的布局可明确列为限制。不能以单元测试关闭TODO中的实战项目。

## 可重复构建

1. 读取AGENTS、TODO、TESTING和已归档性能调查。记录目标提交、Python版本、模型及依赖清单。
2. 在Windows11 x64／Python3.11 x64环境运行 `setup.ps1 -Development`。依赖只用锁定wheel；`pip check`必须通过。官方Python与微软安装器核验SHA256及发布者签名。
3. 执行完整pytest和冻结离线自检。CI必须通过。正式包目前固定CPython3.11.9；更换运行时须更新原生组件清单及许可，不从开发机PATH混入DLL。
4. 使用 `python -m PyInstaller --noconfirm MjsOverlay.spec` 构建。环境变量`MJS_BUILD_NAME`留空得到MjsOverlay.exe。不要从运行中目录收集用户数据。
5. `tools/export_public_source.py 新目录`导出白名单快照；人工核对文件／裁片／历史文档脱敏，不推送私人工作区历史。
6. `tools/build_release.py --frozen dist/MjsOverlay --wheels wheel目录 --installers 安装器目录 --output 新输出目录`生成payload、完整便携、源码、模型、离线wheel、下载器以及90MB分卷。安装器目录必须含manifest.json。此脚本不上传、不自动签名。

依赖更新使用 `tools/lock_dependencies.py`，从下载的wheel生成运行／开发闭包并向PyPI核对哈希。不要直接冻结整个开发环境。原生运行时、Qt源码与模型另列在dependencies.json，第三方许可材料和原始权利声明随包保留。

运行 `python tools/collect_dependency_notices.py wheel目录` 从锁定wheel收集全部内嵌许可；`--check`逐字节核对。打包器会强制检查，FlatBuffers的上游同版本许可也须存在。仅补许可／文档或启动脚本时可复用已测试的EXE，但必须重新打归档并检查新哈希。

## 签名与镜像

RSA3072私钥保存在仓库之外，离线备份；只分发`release/public-key.xml`。对最终release.json原始UTF-8字节运行 `release/sign.ps1 -Manifest 清单路径 -PrivateKey 仓库外私钥路径`。不能在文档、日志或CI输出私钥。哈希不是发布者身份认证；清单签名也不是Windows Authenticode签名。

先准备GitHub草稿Release及Gitee附件。Gitee普通附件不足以放完整大包，上传全部90MB以内分卷，保留稳定文件名。逐个匿名下载核对大小／SHA256后，将真实HTTPS地址加入对应parts.urls，再签名。镜像落后不能降级；只保留本项目登记的当前与上一版镜像资产，清理需核对资产ID，Git标签及GitHub历史不删除。未验证Gitee时`mirror_verified`必须保持false。

将页面实际返回的地址整理为JSON对象（文件名→HTTPS下载地址），运行 `python tools/verify_mirror.py --manifest 候选/release.json --mapping 地址.json --cache 验证缓存 --output 新清单.json`。工具不读取浏览器认证，要求五种镜像角色均可匿名下载，并验证分卷合并后的整包哈希；任何一项失败均不输出可启用清单。随后再次签名，保留匿名验证报告。普通项目页面当前提示总附件配额1GB：上传前核对本项目已有附件总大小和本批大小，保留安全余量，不只检查单附件100MB限制。

签名清单`release.json`／`release.sig`放在两个仓库main根目录，并附在Release。先上传全部字节一致的资产，再公开指向它们的清单；禁止清单先行导致旧客户端自动获取未就绪版本。签名完成后不得再修改ZIP或清单，需修改则重新打包、签名、验证。更新器只接受stable清单和更高版本号。

## 每个公开版本必须接入自动更新

从 1.0.2 起，公开测试版也必须准备更新 payload，并在资产可用后发布兼容 1.0.0 启动器的签名通道。只上传 win64.zip 或只修改 GitHub 的 Latest 标记，不会让已有安装版更新。不得用“去网页下载”代替更新交付；实验性版本在未准备通道前保持草稿或仅本地测试。

保留 schema_version=1、channel=stable、minimum_launcher=1 和现有 RSA 公钥。这里 stable 是旧启动器协议字段，不是实战验收结论。若未来确需升级启动协议，应先交付旧启动器可下载的兼容过渡版，不能直接提高 minimum_launcher 丢下旧用户。

发布前用 GitHub releases API 的当前结果（包含最新公开版本）保存为 JSON，并运行：

```powershell
gh api repos/Henry7682/mjs-overlay-assistant/releases | Set-Content -Encoding utf8 published-releases.json
python tools/check_update_channel.py --manifest 候选目录/release.json --releases published-releases.json
```

检查签名、最高已公开数字版本、旧启动器协议，以及六种附件的 URL／大小／服务器 SHA256。此门禁不代替匿名下载和实际启动握手。顺序：附件上传并验证→发布正文／Latest 状态→核对候选通道→合并签名清单到 main→匿名重读 main→旧版 launch.cmd 升级与配置保持。若网络故障导致中途失败，明确报告通道尚未完成，不声称已更新。

日常用户入口始终是最外层 launch.cmd；Windows 快捷方式须指向它。重复启动已有实例只唤出设置，不中断对局。下载或新版本启动失败继续使用／回退旧版；不移除验签和配置备份。源码开发目录只提示，不自动覆盖开发者修改；历史内部 EXE 绕过启动器是明确边界，不能靠服务器更改旧二进制行为。管理员权限只用于目录写入确有需要时，不作为所有用户默认要求。

Gitee 由维护者手动同步时，必须一起同步 main 的 release.json／release.sig；只导入源码或只上传 ZIP 不等于同步更新。镜像附件未经匿名验证仍保留 mirror_verified=false。GitHub 不可达且 Gitee 尚旧时，客户端可能只能离线启动旧版，不能宣称任意网络都能更新。

## 必须保存的发布证据

- 干净Windows：无开发环境依赖的冻结启动、源码哈希安装、四榜／三模型、设置页和UIA初始化。
- 安装／更新：断网、错误签名、分卷损坏、危险ZIP、旧配置保持、新版失败与中断回退、镜像落后／不可用。
- 诊断：关闭不留新图、仅目标窗口、容量与保留、导出前预览、公开包无意外原图、只读安全回放；性能按同素材交错测量。
- 现有四模式回归和实战TODO分别记录，注明不能复现的Windows外部接口时序。
- 资产SHA256、发布提交、依赖／许可证清单、CI链接、实际匿名下载URL及镜像核验时间。

确认以上后公开`v1.0.0`普通Release，并在标题、正文和README明确“公开测试版，招募测试与反馈”。反馈QQ群104720192；原图私聊群主／管理员，不能把私人素材附在Release。
