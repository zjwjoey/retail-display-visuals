# 商超陈列效果图 Skill

V1.3用于商超、家居卖场和样品展厅的陈列效果图制作。货架模板引擎提供11张基础底图、38个起始格位，并支持导入自有图片新建模板、复制基础模板、自定义格位与保护区、保存/恢复模板包及选择上货。具备尺寸校验、分批生图任务与漂移提示；继续支持完整墙、大景、局部改造和成套输出。

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

- [货架模板引擎](references/shelf-template-engine.md)：本地控制台、逐格选品、编译和复核命令；[模板目录](assets/shelf-templates/catalog.json)与[实际失败边界](references/template-engine-validation.md)。
- [Skill 入口](SKILL.md)：模式选择、参考图处理、生成与修订流程。
- [陈列规则](references/display-rules.md)：分区、支撑、密度、标签及空间关系。
- [需求与提示词模板](references/prompt-templates.md)：近景、大景、编辑和配套流程。
- [验收表](references/qa.md)：检查实际成图，区分通过、需改和无法判断。
- [场景配置](references/scene-spec.md)与[JSON示例](references/scene-spec.example.json)：固定模块、层位与视图关系，使用scripts/scene_spec.py核查和导出。
- [真实零售规范](references/retail-realism.md)：主题专区与综合门店、包装、相对尺寸及编辑边界。
- [回归测试](references/regression-plan.md)与[实测状态](references/validation-status.md)：记录首轮与后续实际结果。
- [配套示例](references/paired-example.md)：完整设定和可直接使用的两套提示词。
- [素材说明](references/source-guide.md)：145张素材索引、14张联系表及使用边界。
- [AI 图逐张评审](references/ai-reference-review.md)：76张各自的优点、限制和查看方式。
- [门店观察](references/store-observations.md)、[展厅观察](references/showroom-observations.md)：可见事实与规则依据。

## 素材与验证范围

本仓库包含原参考资料的索引和联系表，未包含145张原始大图。另含本轮11张货架模板和5种商品示例原图，模板与样例路径可随Skill迁移。旧索引中的本机绝对路径仅用于原作者环境；在其他机器使用时，可按 `relative_path` 与新的素材根目录重新定位，或提供自己的参考图。

76张AI图均经过联系表审阅，其中10张另开原图核查。V1已完成首轮四类型出图，概念效果基本可用；不等于商品保真、真实门店方案与多视角一致性已全部通过。V1.1的实际回归结果见实测状态。配置校验不看图片，不能替代视觉验收。示例中的层数、模块、颜色和布局属于概念设定；图片不能用于认定真实尺寸、库存、承重或经营效果。
