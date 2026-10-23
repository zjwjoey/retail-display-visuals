# 商超陈列效果图 Skill

用于商超、家居卖场和样品展厅的陈列效果图制作。支持完整货架墙近景、空间大景，以及两种视角的成套输出。

## 安装与调用

在 PowerShell 中运行（目标目录须不存在）：

```powershell
git clone https://github.com/zjwjoey/retail-display-visuals.git "$env:USERPROFILE\.codex\skills\retail-display-visuals"
```

调用示例：

```text
使用 $retail-display-visuals，根据参考照片制作一套家居陈列效果图：
一张完整货架墙近景，一张包含该墙的空间大景。
用途为门店零售，使用白色货架。
```

需要当前环境提供图像生成或编辑工具；Skill 本身不包含模型或 API 凭证。也可以只分析参考图、规划布局或输出提示词。

## 内容

- [Skill 入口](SKILL.md)：模式选择、参考图处理、生成与修订流程。
- [陈列规则](references/display-rules.md)：分区、支撑、密度、标签及空间关系。
- [需求与提示词模板](references/prompt-templates.md)：近景、大景、编辑和配套流程。
- [验收表](references/qa.md)：检查实际成图，区分通过、需改和无法判断。
- [配套示例](references/paired-example.md)：完整设定和可直接使用的两套提示词。
- [素材说明](references/source-guide.md)：145张素材索引、14张联系表及使用边界。
- [AI 图逐张评审](references/ai-reference-review.md)：76张各自的优点、限制和查看方式。
- [门店观察](references/store-observations.md)、[展厅观察](references/showroom-observations.md)：可见事实与规则依据。

## 素材与验证范围

本仓库包含索引和联系表，未包含145张原始大图。索引中的本机绝对路径仅用于原作者环境；在其他机器使用时，可按 `relative_path` 与新的素材根目录重新定位，或提供自己的参考图。

76张AI图均经过联系表审阅，其中10张另开原图核查。第一版已完成文件结构、引用和素材索引校验，尚未完成新生图的稳定性实测。示例中的层数、模块、颜色和布局属于概念设定；图片不能用于认定真实尺寸、库存、承重或经营效果。
