<p align="center"><img src="assets/logo.png" width="112" alt="ocrmath logo"></p>

# ocrmath

> 截屏公式识别与 PDF 转换工具。Mathpix 与大模型两种服务可选：Mathpix 支持多格式转换，大模型支持截图转 LaTeX/Markdown、PDF 逐页转 Markdown。

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green) ![Platform](https://img.shields.io/badge/platform-Windows-lightgrey) ![License](https://img.shields.io/badge/license-MIT-orange)

---

版本变更见 [CHANGELOG.md](CHANGELOG.md)。

## 功能

| | |
|---|---|
| **截屏公式识别** | 全局快捷键唤起 → 鼠标拖选公式区域 → 自动识别 → 一键复制 LaTeX |
| **可切换大模型** | 默认 gpt-6-luna，模型名与 Responses API 地址可配置；保留 Mathpix，截图与 PDF 可分别选择服务 |
| **LaTeX 实时预览** | 结果窗口内置 MathJax 矢量渲染，所见即所得，支持中英公式与中文混排 |
| **复制即隐藏** | 复制后浮窗自动隐藏到托盘，并记住窗口位置、复制格式和 PDF 选项 |
| **专注浮窗** | 紧凑结果窗口，原图按需展开；纯公式提供预览 / LaTeX，混排内容提供预览 / Markdown；底部一键切换识别服务，直达 PDF、历史、用量与设置 |
| **本地缓存** | SHA256 去重，相同区域第二次识别零成本零网络 |
| **历史记录** | 工具窗口「历史」页：搜索 / 复制 / 重新打开 / 删除 |
| **PDF 转换** | 拖拽 PDF → 选输出格式（MMD/MD/DOCX/TeX/HTML/带文字层 PDF）→ 异步进度条 |
| **PDF 任务恢复** | 保存远端任务 ID，重启后继续处理；重试只补下载缺失或已修改的结果，按任务去重统计页数 |
| **用量与费用** | 「用量」页按今日 / 本月 / 全部汇总 Mathpix 与大模型花费 |
| **Token 用量** | 大模型请求按模型统计输入、缓存输入、输出 token 和费用；可按模型设置单价 |
| **WebDAV 加密同步** | 可选：把计数器、凭证和大模型设置在本机加密后同步到自建 WebDAV（Nextcloud 等），服务器只有密文 |
| **托盘常驻** | 关闭窗口后留在托盘；识别中托盘图标闪烁状态指示 |
| **可自定义快捷键** | 设置页中按下任意组合键即可记录 |
| **加密凭证存储** | Windows DPAPI 与当前用户绑定，明文不落盘 |

## Mathpix 成本（来源：[Mathpix Pricing](https://mathpix.com/pricing/api)）

| 操作 | 单价 | 100 次/月 |
|---|---|---|
| 截屏识别 (`/v3/text`) | **$0.002 / 张** | $0.20 |
| PDF 转换 (`/v3/pdf`) | **$0.005 / 页** | $0.50（按 100 页） |

PAYG 一次性 $19.99 启动费。含 12 行以上文本的图像按 PDF 单价计费。应用内单价可在设置中调整，统计随之更新。

## 安装

### 方式 A：使用安装包（推荐普通用户）

1. 到 [Releases](https://github.com/vvangpc/ocrmath/releases) 下载最新 `ocrmath-setup-x.y.z.exe`
2. 双击安装（per-user，无需管理员），按提示完成
3. 从开始菜单或桌面打开 **ocrmath**

### 方式 B：从源码运行（开发者）

需要 Python 3.10+（推荐 3.13 及以上）。

```powershell
git clone https://github.com/vvangpc/ocrmath.git
cd ocrmath
pip install -r requirements.txt
python main.py
```

## 申请 Mathpix API Key

1. 注册 [accounts.mathpix.com](https://accounts.mathpix.com/)
2. Console → API Keys 创建一组 `app_id` 和 `app_key`
3. Console → Billing 切换到 **Pay-as-you-go** 套餐
4. 启动 ocrmath，首次运行会打开设置页让你填入凭证

## 使用

### 配置大模型

在「设置」中分别选择截图识别和 PDF 转换的服务。使用大模型时填写：

- **API Key**：在 OpenAI API 平台或兼容服务上创建的密钥。
- **模型**：默认 `gpt-6-luna`，可直接填写其他模型 ID，无需修改代码。
- **API Base URL**：默认 `https://api.openai.com/v1`。兼容服务必须支持 Responses API；截图需要图像输入能力，PDF 需要 `input_file` PDF 视觉输入能力。只有 Chat Completions 接口的服务目前不支持。

密钥在 Windows 下与其他设置一起用 DPAPI 加密保存在本机。配置 WebDAV 后，Mathpix 和大模型的密钥、模型、地址和单价会用同步口令加密后再上传（scrypt + AES-256-GCM），下载后在本机解密；口令只保存在本机，不会上传。选择大模型后无需填写 Mathpix 凭证；如仍选择某一路使用 Mathpix，则需保留对应凭证。浮窗和 PDF 页面也可分别切换服务，已有结果继续显示原识别服务的信息。

大模型接口按 [OpenAI 图像输入](https://developers.openai.com/api/docs/guides/images-vision)与 [PDF 输入](https://developers.openai.com/api/docs/guides/file-inputs)接入。模型的识别准确率和实际账户权限需用自己的材料与密钥验证。

### 大模型 PDF 逐页转 Markdown

选择「大模型 · Markdown」后，每次请求仅发送一页 PDF，保留页内公式的 LaTeX 表达。可填写 `2,4-6` 这样的页面范围，重复页码去重，按原文顺序输出。程序在后台保存源文件副本、每页文字及任务配置，完成后合并成 `.md`；不包含 Word、原版式还原或带文字层 PDF，其他格式仍可选择 Mathpix。

中途失败或暂停后，点击任务的「继续」只处理尚未保存的页面。每个任务固定原 API 地址、模型和识别提示版本，更改默认模型不会改变已有任务；恢复时需要原 API 地址的有效密钥。完整结果文件丢失时可从已保存的页面文字重新导出，无需再调用 API。原文件删除后，只要本机任务副本仍在即可继续识别。

截图缓存与 PDF 页面缓存按 API 地址、模型和提示版本隔离。相同页面可跨任务命中缓存；本地缓存命中不会新增 API token。API 连接超时不会自动重发，以避免不确定的重复消耗；手动重试可能再次计费。未完成或拒绝的模型响应不会当作识别结果，但返回的 token 用量仍会记录。

「用量」页展示本机实际收到的 API usage；缓存输入是输入 token 的子集，不能重复相加。在「设置 → 偏好与单价」中可按模型填写每百万 token 的单价，费用按请求发生时的单价记录，改价不影响历史，设置单价前的请求保持“未定价”，不计入合计。不返回 usage 的兼容服务会标注未知次数；连接中断而未收到响应的消耗需以服务端账单为准。Token 明细只统计本机请求，不与 WebDAV 同步。

### 截屏识别

1. 打开 OCRmath 后，点击浮窗底栏的服务按钮切换 Mathpix 或大模型。点击「截图识别」、按全局快捷键（默认 `Ctrl+Alt+M`）或点击托盘图标
2. 屏幕变暗后用鼠标拖选公式区域，松开
3. 等待 1–2 秒，结果窗口弹出
4. 纯公式复制 LaTeX，混合文本复制 Markdown；也可切换到对应标签查看源码。LaTeX 标签中可选择纯源码、行内 `$…$` 或独立 `$$…$$`
5. 点击右上角的图片按钮对照原图。点击复制或按 `Ctrl+Shift+C` 后，浮窗自动隐藏到托盘，双击托盘图标可再次打开；`Esc` 也可隐藏浮窗

软件会在本机记住窗口位置和大小、LaTeX 复制格式、PDF 输出格式与手动选择的输出目录，重启后继续使用。这些记录不参与 WebDAV 同步。

截图识别失败时，浮窗保留原图和错误信息，点击「重试原图」即可重试。识别期间锁定服务与截图操作；截图前临时隐藏应用窗口，取消选区后返回浮窗。

浮窗底部的「PDF」「历史」「用量」打开工具窗口，关闭工具窗口或点击「返回浮窗」会回到原识别结果。「设置」按识别服务、偏好与单价、同步分组。关闭浮窗后仍在托盘常驻。

### PDF 转换

1. 在浮窗底部点击「PDF」
2. 拖入 PDF 或点击选择
3. 勾选所需输出格式：
   - **MMD** — Mathpix Markdown，公式用 `$...$` 保留 LaTeX，适合 Typora / Obsidian
   - **MD** — 标准 Markdown，适合 GitHub / 通用编辑器
   - **DOCX** — Microsoft Word
   - **TeX zip** — LaTeX 源文件
   - **HTML** — 网页
   - **带文字层 PDF** — 原 PDF 但可选中复制文字
4. 输出目录默认与所选 PDF 同目录
5. 点「开始转换」，进度条流畅推进，完成后自动打开输出文件夹

带文字层 PDF 保存为 `原文件名_ocr.pdf`，保留源文件；输出重名时自动添加编号。下载完整后才保存为正式文件，失败或取消时清理本次下载的临时文件。取消会在下一次收到下载数据时生效，网络阻塞时仍需等待请求返回或超时；已提交的服务端转换不会因此撤销。

### 恢复 PDF 任务与补下载

在「PDF」页的任务列表中找到任务，点击「继续」或「补下载」。程序沿用已保存的远端任务 ID，不重新上传 PDF；原始文件已移动或删除也可恢复。重试保留原输出目录和格式，校验已保存文件的 SHA-256，仅下载缺失或内容已变化的结果。用户修改的文件会保留，新下载结果自动编号。

任务记录保存在本机 `pdf_jobs.db`，包含任务 ID、输出路径、选项和进度，不保存 API 密钥。恢复时需使用原 app_id 的有效凭证。页数按任务累计去重，恢复后发现新增页数才补记；本地统计仍是估算，并非服务端账单对账。

如果上传时断网、未收到任务 ID，程序不会自动重新提交，需先检查 Mathpix 端是否已接收。远端任务或输出过期后无法恢复，也不会自动产生新的上传。当前任务选择框显示最近 100 条记录。

### WebDAV 多机计数

新版使用共享历史基数加各设备的独立增量：同一设备取最大值，不同设备相加，反复同步不重复计数。旧总数按最大值迁入历史基数；旧版此前遗漏的独立增量无法还原。

配置的路径仍可保持 `/ocrmath/sync.json`，新版实际使用同目录的 `sync.v3.json`，内容全部加密。每台设备都要在「设置 → 同步」填写同一个同步口令（至少 8 位）；未填写时同步会暂停，不会上传明文。口令忘记后无法恢复远端数据，可以用新口令覆盖远端，其他设备改用新口令后会把各自的数据合并回来。

升级后首次同步会把旧版的明文文件（`sync.v2.json` 和配置的路径）合并进加密文件，上传成功后再删除它们；删除失败时设置页会提示手动删除。如果密钥曾以明文同步到不完全可信的服务器，建议到 Mathpix 和大模型平台更换密钥。**请升级所有参与同步的设备**；旧版设备读不了加密文件，也不会覆盖它。每台设备在本机生成独立标识，请通过 WebDAV 同步，不要复制本地配置来克隆设备。

服务器需要提供强 ETag 并支持条件写入。程序使用 `If-Match` / `If-None-Match` 防止并发覆盖，冲突后重新读取、合并并重试，最多 4 次；不支持时明确报错，保留本地数据。

### 历史记录

切到「历史记录」标签页，可：

- 搜索（300ms 节流），缩略图在后台线程加载，不阻塞界面
- 单击 / 双击行 → 重新打开结果窗口
- 复制 LaTeX
- 删除单条 / 清空整库

## 数据目录

```
%APPDATA%\ocrmath\
├── config.dat      # DPAPI 加密的凭证 + 快捷键 + WebDAV 配置
├── ocrmath.db      # SQLite：识别结果缓存、历史索引、使用记录
├── pdf_jobs.db     # PDF 任务 ID、输出记录与恢复状态（不含密钥）
├── llm_usage.db    # 本机大模型 token 账本与 PDF 页面缓存（不含密钥）
├── pdf_sources\   # 大模型任务的本地源 PDF 副本，用于恢复
├── cache\          # 截屏 PNG 文件（按 SHA256 前两位分桶）
│   ├── ab\
│   │   └── ab12...ef.png
│   └── cd\...
└── mathjax\        # tex-svg.js（安装版自带，首次启动复制；源码运行时联网下载）
```

## 项目结构

```
main.py                # 启动入口
ocrmath/
├── app.py             # 托盘、全局快捷键、识别调度和后台同步
├── core/              # 不依赖具体界面的基础能力
│   ├── config.py      # DPAPI 加密的设置读写
│   ├── storage.py     # SQLite 缓存、历史、使用记录和 PNG 文件
│   ├── counters.py    # 多设备计数的幂等合并
│   ├── webdav.py      # WebDAV 同步
│   ├── sync_crypto.py # 同步文件的本地加解密
│   └── utils.py       # 费用格式化和用户错误类型
├── ocr/               # 识别服务
│   ├── image_client.py、pdf_client.py  # Mathpix 接口
│   ├── llm_client.py、llm_pdf.py       # 大模型 Responses API 与 PDF 逐页识别
│   ├── llm_store.py   # 大模型 token 账本与页面缓存
│   ├── pdf_jobs.py    # PDF 任务持久化
│   └── pdf_service.py # PDF 任务流程：创建、恢复、计费、进度
└── ui/                # 界面
    ├── windows.py     # 浮窗与工具窗口
    ├── bridge.py      # 页面与 Python 之间的唯一入口
    ├── result_format.py、settings_service.py  # 浮窗规则与设置校验
    ├── snipper.py     # 全屏截图选区
    ├── mathjax_view.py、styles.py、ui_icons.py
    └── web/           # HTML / CSS / JS 页面
assets/                # 应用图标和 logo
installer/             # Inno Setup 安装脚本与语言文件
tools/                 # 生成图标、提取发布说明、手动 API 测试
tests/                 # 单元测试
build.spec             # PyInstaller 打包配置
```

## 自行打包

需要机器安装 [Inno Setup 6.5+](https://jrsoftware.org/isdl.php)（内置的中文语言文件已随仓库提供在 `installer\ChineseSimplified.isl`，要求 6.5 及以上版本编译）。

```powershell
pip install pyinstaller
python -m PyInstaller build.spec --clean
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\ocrmath.iss
```

输出在 `dist\installer\ocrmath-setup-x.y.z.exe`。

- 发版号只在 `pyproject.toml` 维护：`build.spec` 会把它写入 `installer\version.iss` 供 Inno Setup 使用，所以要先跑 PyInstaller 再编译安装包；CI 会拒绝与该版本号不一致的 tag。
- `build.spec` 会把固定版本的 MathJax 下载到 `vendor\`（校验 SHA-256）并打进安装包，用户首次启动无需联网。
- 运行依赖只在 `requirements.txt` 维护，`pyproject.toml` 从中读取。
- 改了 `ocrmath/ui/ui_icons.py` 的 `render_logo` 里的 logo 后，运行 `python tools/make_icon.py` 重新生成 `assets/icon.ico` 和 `assets/logo.png`。

## 测试

单元测试只用标准库 `unittest`，无需额外安装，也不会碰真实配置或网络：

```powershell
python -m unittest discover -s tests -t .
```

CI 在打包前会先跑这些测试。

## API 烟雾测试（不打开 GUI）

`tools/try_image_api.py` / `tools/try_pdf_api.py` 是需要真实凭证的手动冒烟脚本，非自动化单测：

```powershell
$env:MATHPIX_APP_ID = "your_app_id"
$env:MATHPIX_APP_KEY = "your_app_key"

python tools/try_image_api.py path\to\equation.png
python tools/try_pdf_api.py path\to\small.pdf
```

`ocrmath/core/storage.py` 带内置自测：`python -m ocrmath.core.storage --test`（已包含在上面的单元测试中）。

## 故障排查

| 现象 | 处理 |
|---|---|
| 启动报缺少 PyQt6 | `pip install -r requirements.txt` |
| 全局热键不生效 | `keyboard` 库被杀软拦截，可用浮窗按钮替代；或在设置中改其他组合键 |
| 401 / 403 | API Key 错，从托盘菜单 → 设置… 重填 |
| PDF 进度条卡 0% | 网络问题；查看 PDF 标签页底部日志 |
| LaTeX 预览空白 | 安装版自带 MathJax；源码运行首次需联网下载 (~2MB) 至 `%APPDATA%\ocrmath\mathjax\`，如长时间空白请检查网络代理 |
| 多显示器截图错位 | 已按 `QGuiApplication.screens()` 多屏拼接，仍有问题请提 issue |

## 隐私说明

- 图像和 PDF 按所选服务发送到 Mathpix 或配置的大模型 API；默认大模型地址为 OpenAI。选择自定义地址前请确认服务归属。
- API 凭证用 Windows DPAPI 加密，与当前 Windows 用户账户绑定，他人复制走也解不开
- 可选的 WebDAV 同步只连接你自己配置的服务器
- 识别结果缓存在本地 `%APPDATA%\ocrmath\ocrmath.db`
- 大模型 PDF 副本和逐页文字保存在本机以支持恢复；任务副本和任务正文不会随截图历史清空。页面共享缓存按保留天数清理，token 账本保留。
- Mathpix 会保留你提交的源 PDF 30 天、输出文件 90 天，详见 [Mathpix Privacy](https://mathpix.com/privacy)

## 贡献

欢迎 issue / PR。建议优先方向：

- 跨平台支持（macOS / Linux）— 目前 DPAPI 仅 Windows 可用，其他系统使用明文存储
- 自动粘贴到上一焦点窗口（参考 Mathpix Snip）
- 深色模式 QSS

## 许可

[MIT License](LICENSE)

## 致谢

- [Mathpix](https://mathpix.com/) — 提供出色的 OCR API
- [PyQt6](https://pypi.org/project/PyQt6/)
- [MathJax](https://www.mathjax.org/) — 矢量公式渲染
- [keyboard](https://github.com/boppreh/keyboard)
- [Inno Setup](https://jrsoftware.org/isinfo.php)

---

> 本工具与 Mathpix Inc. 无任何官方关联，仅为第三方 API 客户端。
