<div align="center">

# OMRKit v2.2

**零校准光学标记识别（OMR）引擎：支持 3/4 遮挡 ArUco 角点恢复、擦除铅笔痕迹抗干扰、复印偏移局部微对齐、二维码自动模板识别、空白答题卡自动纠偏网格检测、浏览器实时摄像头阅卷、Unicode 矢量 PDF 答题卡生成、经典测试理论（CTT）心理测量分析、FastAPI REST API 与 6 语言 Web Studio。**

[![CI](https://github.com/duhanguler/omr/actions/workflows/ci.yml/badge.svg)](https://github.com/duhanguler/omr/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/omrkit?style=flat-square&color=0D7A52&logo=pypi&logoColor=white)](https://pypi.org/project/omrkit/)
[![在线演示](https://img.shields.io/badge/%E5%9C%A8%E7%BA%BF%E6%BC%94%E7%A4%BA-OMRKit_Studio-1849C6?style=flat-square&logo=render&logoColor=white)](https://omrkit-studio.onrender.com/)
[![Release](https://img.shields.io/github/v/release/duhanguler/omr?style=flat-square&color=111317)](https://github.com/duhanguler/omr/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-0D7A52.svg?style=flat-square)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-111317.svg?style=flat-square)](pyproject.toml)
[![Docker GHCR](https://img.shields.io/badge/Docker-ghcr.io%2Fduhanguler%2Fomr-2496ED.svg?style=flat-square)](https://github.com/duhanguler/omr/pkgs/container/omr)

[**在线演示**](https://omrkit-studio.onrender.com/) · [**PyPI**](https://pypi.org/project/omrkit/) · [部署指南](docs/DEPLOYMENT.md) · [示例数据](examples/) · [贡献指南](CONTRIBUTING.md)

[English](README.md) · [Türkçe](README.tr.md) · **简体中文** · [Deutsch](README.de.md) · [Русский](README.ru.md) · [Español](README.es.md)

</div>

> **在线 Web Studio 演示：** 直接在浏览器打开 **[omrkit-studio.onrender.com](https://omrkit-studio.onrender.com/)**（支持 **EN · TR · ZH · DE · RU · ES** 切换）——点击顶部 **示例数据** 即可一键扫描并批改 5 份试卷，使用放大气泡局部裁切与键盘快捷键（`A–E`、`Backspace`、`↑↓`）快速人工复核，或测试 **实时摄像头** 与矢量 PDF 答题卡生成。*（托管于 Render 免费层，冷启动约需 20–30 秒。）*

---

## 核心特性（v2.2）

- **真实考场光学鲁棒性：**
  - **擦除铅笔痕迹过滤（`erased_dominance_ratio`）：** 通过灰度主导比区分擦除残留与真实多涂，避免误报 `multi_marked`，同时完整捕获真实双选与轻度 HB 铅笔填涂。
  - **3/4 遮挡 ArUco 角点恢复（`aruco_3pt`）：** 当手指、订书钉或折角遮挡任意 1 个定位角时，自动利用其余 3 个标记的 12 个亚像素角点解算精确透视单应矩阵。
  - **复印偏移块级微对齐（`local_refinement`）：** 基于 Sobel 边缘幅值与合成圆环相关匹配（`±6px`），自动将复印或缩放导致的局部偏移吸附回填涂圆心。
  - **自动纠偏空白答题卡网格检测（`omrkit detect-layout`）：** 自动估计并校正 `±12°` 倾斜后聚类识别圆形气泡块，直接生成 `template.json`。
- **零校准矢量 PDF 生成与二维码自动识别：** 一键输出带 ArUco `[0,1,2,3]` 定位角、内嵌自动模板二维码与 TrueType Unicode 字体的 A4/Letter PDF 答题卡及完全对应的 `template.json`；扫描时无需 `-t` 参数即可通过二维码自动匹配模板。
- **形状感知混合识别与校验器：** 同时准确识别常规涂黑、**对号（✓）与叉号（✗）**；内置 **Luhn**、**TC Kimlik No** 等学号/证件校验器，并将低置信度或异常项送入 HITL 人工复核队列。
- **经典测试理论（CTT）与成绩报告：** 自动计算平均分、中位数、标准差、试题难度（$p$）、上下 27% 区分度（$D$）、各选项频次分布与 **KR-20 信度**；支持标准评分、倒扣分策略、多试卷版本（A/B/C/D）、多工作表 Excel（`.xlsx`）及个人 **PDF 成绩单**。
- **6 语言工业级 Web Studio：**
  - **扫描与复核：** 复核卡片内嵌放大气泡条裁切、主图实时 SVG 定位框与键盘快速审核（`A–E`、`Backspace`、`↑↓`）。
  - **模板设计器：** 画布内直接点击拖拽题块、方向键 `1px`（`Shift 10px`）微调、撤销/重做（`Ctrl+Z` / `Ctrl+Shift+Z`）、实时像素坐标显示与旧版 `OMRChecker` v1 模板迁移。

---

## 实际扫描与生成效果

<table>
  <tr>
    <td width="54%" align="center">
      <img src="https://raw.githubusercontent.com/duhanguler/omr/main/docs/assets/scan_overlay_demo.jpg" alt="OMRKit 手机实拍扫描校验叠加图" />
      <br />
      <sub><b>手机实拍扫描：</b> 绿色 = 高置信度识别（含 ✓ 与 ✗），红色 = 多涂，琥珀色 = 进入局部放大人工复核队列。</sub>
    </td>
    <td width="46%" align="center">
      <img src="https://raw.githubusercontent.com/duhanguler/omr/main/docs/assets/generated_sheet_preview.jpg" alt="OMRKit 生成的 ArUco + 二维码矢量答题卡" />
      <br />
      <sub><b>零校准矢量 PDF：</b> A4/Letter 规格，ArUco 四角 [0,1,2,3]、内嵌二维码与精确匹配的 <code>template.json</code>。</sub>
    </td>
  </tr>
</table>

---

## 60 秒快速上手

```bash
# 从 PyPI 安装（推荐）
pip install omrkit              # 核心视觉引擎 + PDF + ArUco/QR + CLI
pip install "omrkit[all]"       # 完整版：包含 6 语言 Web Studio、FastAPI REST API 与 Excel 导出

# 或直接运行官方 Docker 镜像（无需构建）
docker run -p 8000:8000 ghcr.io/duhanguler/omr:latest
```

### 1. 生成可打印的 ArUco + 二维码答题卡

```bash
omrkit generate --preset standard_mcq_40 -o my_exam
# 生成: standard_mcq_40_sheet.pdf, template.json, answer_key.json
```

### 2. 扫描图片或多页 PDF（二维码自动匹配或指定模板）

```bash
# 无需指定模板，通过答题卡二维码自动扫描：
omrkit scan examples/standard_mcq_40q/scans -o outputs/auto_demo

# 指定模板与答案，导出 CSV / JSON / Excel / PDF 个人成绩单：
omrkit scan examples/standard_mcq_40q/scans \
  -t examples/standard_mcq_40q/template.json \
  -k examples/standard_mcq_40q/answer_key.json \
  --policy standard \
  --format csv,json,xlsx,scorecards \
  -o outputs/demo

# 从任意空白答题卡自动检测网格（含 ±12° 自动纠偏）：
omrkit detect-layout examples/turkish_exam_50q/blank_form.jpg -o auto_template.json
```

### 3. 启动 Web Studio 或使用 Python SDK

```bash
omrkit studio
# Web Studio:   http://127.0.0.1:8000
# OpenAPI 文档: http://127.0.0.1:8000/docs
```

```python
from omrkit import AnswerKey, ExamGrader, GradingPolicy, OMRScanner, Template

template = Template.from_file("examples/standard_mcq_40q/template.json")
batch = OMRScanner(template).scan_batch("examples/standard_mcq_40q/scans", workers=4)

key = AnswerKey.from_file("examples/standard_mcq_40q/answer_key.json")
report = ExamGrader(key, GradingPolicy.preset("standard")).grade_batch(batch.sheets)
print(f"已评分 {report.analytics.student_count} 份 | 平均分: {report.analytics.mean_score} | KR-20: {report.analytics.kr20_reliability}")
```

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。Copyright © 2026 Duhan Güler & Contributors.
