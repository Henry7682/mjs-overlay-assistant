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

## 签名与镜像

RSA3072私钥保存在仓库之外，离线备份；只分发`release/public-key.xml`。对最终release.json原始UTF-8字节运行 `release/sign.ps1 -Manifest 清单路径 -PrivateKey 仓库外私钥路径`。不能在文档、日志或CI输出私钥。哈希不是发布者身份认证；清单签名也不是Windows Authenticode签名。

先准备GitHub草稿Release及Gitee附件。Gitee普通附件不足以放完整大包，上传全部90MB以内分卷，保留稳定文件名。逐个匿名下载核对大小／SHA256后，将真实HTTPS地址加入对应parts.urls，再签名。镜像落后不能降级；只保留本项目登记的当前与上一版镜像资产，清理需核对资产ID，Git标签及GitHub历史不删除。未验证Gitee时`mirror_verified`必须保持false。

签名清单`release.json`／`release.sig`放在两个仓库main根目录，并附在Release。先上传全部字节一致的资产，再公开指向它们的清单；禁止清单先行导致旧客户端自动获取未就绪版本。签名完成后不得再修改ZIP或清单，需修改则重新打包、签名、验证。更新器只接受stable清单和更高版本号。

## 必须保存的发布证据

- 干净Windows：无开发环境依赖的冻结启动、源码哈希安装、四榜／三模型、设置页和UIA初始化。
- 安装／更新：断网、错误签名、分卷损坏、危险ZIP、旧配置保持、新版失败与中断回退、镜像落后／不可用。
- 诊断：关闭不留新图、仅目标窗口、容量与保留、导出前预览、公开包无意外原图、只读安全回放；性能按同素材交错测量。
- 现有四模式回归和实战TODO分别记录，注明不能复现的Windows外部接口时序。
- 资产SHA256、发布提交、依赖／许可证清单、CI链接、实际匿名下载URL及镜像核验时间。

确认以上后公开`v1.0.0`普通Release，并在标题、正文和README明确“公开测试版，招募测试与反馈”。反馈QQ群104720192；原图私聊群主／管理员，不能把私人素材附在Release。
