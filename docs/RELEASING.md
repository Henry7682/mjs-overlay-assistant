# 发行身份校验（当前规则）

- `build.ps1` 和 CI 默认生成开发包。包内 build-identity.json 固定版本、渠道、来源提交与 dirty；源码导出亦携带来源，不依赖用户电脑安装 Git。
- 正式候选：先更新版本、提交所有源码、完成 CI，在本地匹配 `v版本号` 标签的干净提交上执行 `build.ps1 -Release`。禁止复用已发布版本和标签。
- 直接调用 PyInstaller 时，正式候选需显式设置 `MJS_RELEASE_BUILD=1`；普通构建不要设置。spec 会校验干净工作树与标签；生成元数据位于构建目录，不修改源码。
- `tools/build_release.py` 另需 `--release`；同时验证 frozen 元数据与当前标签提交一致，拒绝开发包、旧包或未知来源包。其余原有参数和签名要求不变。
- 发布前在本地完成候选安装/升级验证。线上发行与资产就绪后，签名清单通过单独 PR、检查和合并启用，不能直接推 main。未验收资产不能提前进入有效更新通道。
- 本轮仅整理开发身份和入口，不创建1.0.3标签，不改在线1.0.2资产或签名清单；下一次发行预计1.0.3。

以下历史流程与当前规则配合使用；涉及正式打包的旧命令须补上发行模式参数。

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

签名清单`release.json`／`release.sig`放在两个仓库 main 根目录，启动器读取这两个在线地址。Release 附件中的同名清单是发行时的历史快照，不是在线更新入口，不覆盖旧附件。先上传并匿名验证资产，再通过 PR 发布指向它们的签名清单。

仅补充镜像 URL 时，安装包、版本号、大小及哈希保持不变；重新签名清单并同步两个 main 即可，不需要重打安装包或重建 Release。修改包内容则必须使用新版本和新资产，重新构建、校验、签名。更新器只接受 stable 清单和更高版本号。

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


## 国内通道启用与以后每次发行的检查表

1. 在 GitHub 和 Gitee 上传本版本资产；Gitee 大包使用清单规定的分卷。不能把 GitHub 导入源码当作已上传附件。
2. 匿名验证实际 URL、所有分卷及合并后哈希；对最终清单签名。安装包不包含自身未来镜像地址，不存在反复重打包的循环。
3. 清单与签名通过 GitHub PR 和必需 CI 合并；核验镜像没有独立修改后同步 Gitee main，不能覆盖未知维护者提交。
4. 匿名读取两端 main 的 release.json 和 release.sig，检查字节一致、签名有效和目标版本正确；不得只看网页显示上传成功。
5. 用隔离的旧版安装测试 GitHub 不可用时从 Gitee 检查、下载、校验、解压和启动握手，核对配置/榜单不变。记录冷下载与缓存复用的区别。
6. 更新 Release 说明和 TODO/TESTING 中的实际证据。某步失败即标记该通道未完成。

之后按这套流程发布更高版本，正常使用最外层 launch.cmd 的用户会在启动时自动检查与升级，无需手动访问仓库。仅新建 Release 不会自动生成签名清单。现有启动器自动探测 GitHub/Gitee；下载器可用 -Source Gitee 指定本次下载源，但助手设置尚无持久的更新源选择项。断网或所有源失败时启动旧版；已经运行的实例只唤出设置。源码及直接运行内部 EXE 不属于这一启动器自动更新保证。
