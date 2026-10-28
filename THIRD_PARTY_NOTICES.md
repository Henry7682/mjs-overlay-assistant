# 第三方组件与模型

本项目独立实现；未复制 `CXH0920/mjs_agent_project` 的代码或训练数据。

1.0.0 按锁定的 45 份 wheel 逐包核对许可和内嵌通知，完整保留相对目录，索引见 `assets/licenses/dependency-notices.json`（102项）。FlatBuffers 25.12.19 的 wheel 未附 LICENSE，另从上游同版本标签补入 Apache-2.0 原文及来源。`tools/collect_dependency_notices.py` 可重复检查这些文件；打包前必须通过。历史收集目录中额外保留的许可不代表相应组件参与本次分发。

运行与开发依赖分别锁定在 `requirements-runtime.lock.txt`（35项）和 `requirements-dev.lock.txt`（45项），每个发行文件均含 SHA-256。`release/dependencies.json` 记录来源、文件大小、版本、许可及哈希。`requirements.lock.txt` 仅保留历史开发环境记录，不是1.0.0安装入口。

便携包使用 CPython 3.11.9、PySide6 Essentials / Qt 6.12.0、OpenCV、NumPy、RapidOCR、ONNX Runtime、windows-capture、Pillow、httpx、BeautifulSoup 等。各分发包附带的许可、版权与通知文件保存在 `_internal/assets/licenses/`（源码为 `assets/licenses/`），请连同便携目录保留。PySide6 Addons、Qt PDF、WebEngine不参与分发。两个OpenCV发行包分别由上游依赖声明要求，版本与哈希均锁定；不自行删除其中之一造成元数据依赖缺失。

模型来自 RapidOCR 3.10.0 的官方默认模型注册表；上游为 PaddleOCR，权重归 Baidu / 相应 PaddleOCR 权利人。模型未经重新训练，仅重命名为固定本地文件：

| 本地文件 | RapidOCR 原名 |
| --- | --- |
| det.onnx | PP-OCRv6_det_small.onnx |
| rec.onnx | PP-OCRv6_rec_small.onnx |
| cls.onnx | ch_ppocr_mobile_v2.0_cls_mobile.onnx |

SHA-256 与大小记录在 `assets/models/manifest.json`。RapidOCR 的 `MODEL_LICENSES.md` 和 `LICENSE` 一同随包附带，包含上游地址与模型转换说明。

PySide6 / Qt 使用动态链接库，原有 DLL 保留独立文件；本项目未修改其源码。分发使用可用的 LGPL-3.0 路径，Qt及其第三方各文件仍以原有声明为准。Qt LGPL/GPL许可、例外及 QtBase / QtSvg 的第三方归属材料已放入 `assets/licenses/Qt-OpenSource`、`QtBase-6.12.0`、`QtSvg-6.12.0`。主要对应源码：

- [CPython 3.11.9 源码](https://www.python.org/ftp/python/3.11.9/Python-3.11.9.tar.xz)（PSF许可及内部第三方通知见源码LICENSE）。
- [Qt for Python 6.12.0 源码](https://code.qt.io/cgit/pyside/pyside-setup.git/tree/?h=v6.12.0)。
- [QtBase 6.12.0 源码](https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/qtbase-everywhere-src-6.12.0.tar.xz)。
- [QtSvg 6.12.0 源码](https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/qtsvg-everywhere-src-6.12.0.tar.xz)。

用户可研究、调试、重新构建并以兼容DLL替换这些动态链接组件；本项目不限制为调试此类修改而进行的逆向工程。建议复制整个版本目录，在副本中替换并直接运行EXE，或从完整源码重新构建；自动更新器会拒绝被修改的发行文件，开发副本不要作为自动更新安装目录。应用源码与构建脚本均公开，无专有静态对象依赖。重新分发时请保留相应许可、通知及取得对应源码的说明。

《名将杀》的名称、角色、榜单原图及相关素材归各自权利人。本助手不代表游戏官方。用户的实战截图不打入分发包。

0.2 的 Windows 界面自动化使用 pywinauto 0.6.9、comtypes 1.4.17、pywin32 312。仅操作“名将小助手”的公开界面；推荐内容属于小程序及相应作者，不是本助手自有数据库，也不代表合作或官方授权。推荐结果只保留于当前局内存，不随源码或便携包分发。
