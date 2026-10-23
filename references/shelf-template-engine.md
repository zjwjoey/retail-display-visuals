# 货架模板引擎（V1.3 / engine 0.2）

## 何时使用

用户提供空架底图、要求按格位上货或重复生成同机位方案时，使用模板引擎。保留用户底图，先检查标定范围，再编译计划。自由概念大景仍走原流程。

资源入口：`assets/shelf-templates/catalog.json`。现有8张用户模板加3张新生成模板，共11张、38个可见格位。E001–E008只标定各自指定的局部范围；N01为正面双模块四层墙，N02为三排四钩加两层托板，N03为三层低端架。它们没有被确认是同一门店的不同机位。

## 操作

在Skill根目录运行，需要Python与Pillow。依赖声明见requirements.txt；本次实际使用Pillow 12.3.0。图像生成仍使用当前环境内置工具，不需要API密钥；Python编译器本身不调用模型。

```powershell
python -m pip install -r requirements.txt
python scripts/shelf_engine.py gallery assets/shelf-templates/catalog.json --out work/template-console-v1
```

打开生成的index.html，所有页面都可在本地离线使用：

- **基础模板**：现有11张是起始选择，可直接上货；打开标定器后点“另存为自定义模板”，建立带独立ID的副本。基础配置和底图保持。
- **我的自定义模板**：“新建自定义模板”导入PNG/JPEG/WebP空架原图，添加/移除/排序格位及保护区，设置层板/挂钩/筐/桌面支撑方式，再拖动角点、支撑线与挂点。新建矩形和挂点只是示意，必须手动对齐原图。可以修改名称与带来源的宽高深。
- “保存到我的模板”写入当前浏览器的IndexedDB，返回目录后可重复选用；“导出模板包”下载.shelf.json，包含原图原字节、哈希和完整配置，能跨浏览器/机器恢复。浏览器存储与本机文件库是两个存储位置；清理浏览器数据会影响前者，模板包可恢复。浏览器若限制file://存储，可在生成目录运行python -m http.server --bind 127.0.0.1并用固定本机地址访问。
- 自定义工作台也支持逐格选品与上货计划导出。浏览器页面不直接写入本机Skill或调用生图模型；将模板包注册到本机库后，同一计划即可进入原编译/生成流程。

- “打开标定器”：选择格位，分别拖动四角、黄色支撑线端点、橙色挂点。下载配置后放回原templates目录，或调整image.path。重新validate；下载不会自动覆盖原配置。
- “选择商品上货”：逐格选择商品、姿态、正面数量和纵深数量，下载shelf-plan JSON。未选格位保持当前底图原样。这个界面只导出计划，不在浏览器内生图或认证尺寸。
- 自有商品：编辑products/library.json添加参考路径、名称、姿态包络尺寸和身份约束，再重建控制台。商品参考须先单独看图。路径相对于library.json；下载的计划会转换成当前机器的绝对路径。
- 宽高深未知时填null，不能为通过校验编造尺寸。实际尺寸有来源时记录user_measured或manufacturer_spec。concept_assumption仅用于设计假设，不能声称已实测。

注册浏览器导出的自定义模板包，使用单独的用户库（示例目录位于Skill目录外），再合并基础和自定义目录：

```powershell
python scripts/shelf_engine.py import-template "CUST-example.shelf.json" --library "../my-shelf-templates"
python scripts/shelf_engine.py gallery assets/shelf-templates/catalog.json --custom-catalog "../my-shelf-templates/catalog.json" --out work/my-console-v1
python scripts/shelf_engine.py compile "../my-shelf-templates/templates/CUST-example.json" "CUST-example-plan.json" --out work/custom-job-v1
```

示例文件名须换成实际导出ID。import-template核查原图哈希、尺寸、格式与几何，原字节复制图片，并重设库内相对路径；不沿用模板包指定的写入路径。同ID已有文件时拒绝覆盖，修改后需要在工作台“另存副本”生成新ID再导入。合并目录保留基础分组；同一ID同时在浏览器和已注册库中出现时，优先显示浏览器的可编辑卡片。自定义模板库不自动上传远端，也不依赖Skill更新来保存。

命令示例：

```powershell
python scripts/shelf_engine.py validate assets/shelf-templates/templates/N01.json --plan assets/shelf-templates/examples/N01_halloween.json
python scripts/shelf_engine.py compile assets/shelf-templates/templates/N01.json assets/shelf-templates/examples/N01_halloween.json --out work/N01-v1-stage1
```

编译会输出：

| 文件 | 用途 |
|---|---|
| job.json | 阶段、商品引用、格位、输入哈希及可交给宿主工具的tool_request |
| profile-snapshot.json | 本次模板配置字节快照，源配置后来修改不会破坏本次核查 |
| edit-mask.png | 新绘制的黑白语义引导图：白色上货，黑色保持 |
| prompt.txt | 实际任务提示词，含格位像素坐标与归一化坐标 |
| scene-spec.json | 请求的最终陈列计划，兼容V1.1校验器；不代表本阶段成图已实现全部格位 |
| slot-editor.html | 本次格位标定界面 |

宿主执行：读取job.json，先查看底图、商品参考和mask，再把tool_request的prompt、referenced_image_paths、transparent_background原样交给内置image_gen。不要把整个job对象当工具参数。生图后复制到项目目录的result.png，检查格位、数量、姿态、SKU与保护区。

当前工具适配器最多引用5张：1张底图、1张语义mask、最多3张独立商品参考。N01示例4种商品因此分两步。第一步检查后，用其实际输出继续第二步：

```powershell
python scripts/shelf_engine.py compile assets/shelf-templates/templates/N01.json assets/shelf-templates/examples/N01_halloween.json --out work/N01-v1-stage2 --stage 2 --base work/N01-v1-stage1/result.png
python scripts/shelf_engine.py compare work/N01-v1-stage2/job.json work/N01-v1-stage2/result.png --out work/N01-v1-stage2/drift-report.json
```

输出目录不覆盖；每次用新版本目录。后续阶段必须显式提供底图；编译器只检查文件和比例，不会认证这张底图已经视觉通过。第一步存在不影响本轮测试的缺陷时可继续收集证据，但不能把继续执行视为批准。

## 配置约定

template的slots按模块内从上到下排列，id如A/L1、A/H1。polygon是四角凸四边形，坐标0–1；support_line是承托线或挂点行；anchors是可见挂点。protected_regions从可编辑范围中扣除；未选格位也保持。修改镜头或底图尺寸需要重新标定；原图哈希变化直接阻止编译。

plan的bindings指定slot_id、product_id、orientation、front_count、depth_count、gap_cm。products声明reference_path、identity_constraints、dimensions_cm和display_envelopes_cm。orientation可用upright、stacked_flat、hanging、binned；不同姿态必须使用对应外接尺寸，不能拿直立盘高度当叠放高度。样例是概念陈列数量，不是库存。

支持方式、正整数数量、挂点数量、已知宽高深与间隔的溢出会被拒绝。宽度计算为商品外接宽×正面数+间隔×(正面数−1)，深度同理。它不解决曲面嵌套、形变、斜放或复杂3D碰撞。

## 控制与验收边界

可确定控制的是：输入文件与版本、格位合同、参考分批、尺寸拒绝条件、语义引导图、阶段记录和对比报告。当前内置工具没有暴露此适配器可用的硬mask接口，因此mask_enforcement始终是reference_only；不能称为像素锁定、ControlNet、3D货架重建或任意视角一致引擎。

compare只做尺寸比例检查及对齐缩放后的RGB差异，分别统计非目标区、保护区、未选格位。12/255是未经校准的提示阈值，不能检测或证明挂钩数、层数、SKU身份；低差异也可能存在盘子姿态错误。因此visual_verdict始终requires_review，pixel_identity_verified始终false。可见越界或结构改变时即使差异低，也判需改。

样例和失败证据见[本轮实测](template-engine-validation.md)。实际严格编辑无法满足时保留失败，不通过程序合成掩盖模型修改的区域。重试遵守原Skill的定向修订规则。
