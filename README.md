# 寻祎居 · 5S 创作与 VQA 专业视觉审核

通用版 v2.0.1。用于原创生图、参考图复现、局部修复、超分和视觉交付验收。5S 负责定义创作约束，VQA 负责检查成图、记录证据并提出定向修复。风格库可扩展，适用于摄影、插画、动画、水墨和其他视觉媒介。

[下载 v2.0.1 安装 ZIP](https://github.com/l2535305968-crypto/5S-VQA-/releases/download/v2.0.1/xunyi-visual-system-v2.0.1.zip) · [版本记录](CHANGELOG.md)

## 使用方式

1. 下载并解压 ZIP，将整个 `xunyi-visual-system` 文件夹放入支持 Skill 的工具目录，保留文件结构。
2. 如果工具支持按路径读取，直接指定 [SKILL.md](SKILL.md) 作为入口并保留同目录的配套文件。
3. 在对话中说明任务和用途，并提供待审核图片、参考图或母版，以及目标尺寸、格式等硬性要求。可按任务只调用 VQA 或使用完整的 5S → 生成 → VQA 流程。

可直接使用的指令：

- 「按 5S 生成一张壁纸，完成后用 VQA 检查成图，并核验实际像素和格式。」
- 「只用 VQA 审核这张图。请列出影响交付的缺陷，并给出具体位置和修复动作。」
- 「核验这批 PNG 是否达到 2160×3840，输出 100% 原像素裁切和批次结果。」
- 「为这个混合媒介建立临时风格档案，审核时保留有意的笔触和颗粒。」

## 包含内容

| 位置 | 内容 |
| --- | --- |
| [SKILL.md](SKILL.md) | 调用入口、任务模式及读取顺序 |
| [01_Standards](01_Standards) | 原版 5S 创作规范、VQA 七维审核与协同规范 |
| [02_Style_Registry](02_Style_Registry) | 开放式风格注册表、示例、模板和校验规则 |
| [03_Templates](03_Templates) | 审核报告、缺陷反馈及交付溯源模板 |
| [04_Scripts](04_Scripts) | 技术检查脚本与用法 |
| [05_Tests](05_Tests) | 自动化测试，图像测试样本由程序临时生成 |

## 技术检查

图像检查脚本需要 Python 3.10+ 和 Pillow。严格校验风格档案时还需要 jsonschema。在技能目录运行：

```sh
python -m pip install Pillow jsonschema
python 04_Scripts/image_qc.py picture.png --target 2160x3840 --format PNG
python 04_Scripts/image_qc.py images/ --recursive --target 2160x3840 --format PNG --out audit_batch
python 04_Scripts/validate_registry.py --strict
python -m unittest discover -s 05_Tests -v
```

脚本核验实际尺寸、格式、透明通道等文件信息，生成原像素裁切和审核报告。原生分辨率要用生成记录验证。视觉审核结合母版对照、裁切和创作意图，判断材质、结构、风格及伪影。交付时分别记录技术结果、视觉结果和来源证据。

新风格可以先建临时档案用于当前任务，经过用户确认后再登记到正式风格库。

作者：寻祎居
