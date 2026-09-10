# 模式 4：热点实时推送（单次生成）

## 使用

在项目目录创建虚拟环境、安装依赖并配置（已有配置不要覆盖）：

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp config_example.py config_private.py  # 仅首次，无配置文件时执行
```

在本机编辑 `config_private.py` 填入账号和 DeepSeek 配置，随后运行：

```bash
python agent.py
```

选择 `4`，输入 `24`、`72` 或 `168`（回车默认 24）。程序扫描近期候选，按热词与互动筛选最多 30 帖，抓取评论，先导出素材，再输出话题概述、主要讨论和出处。材料足够时汇总 5～10 个话题，不强凑数量。完成后返回菜单。仅终端增加此模式，Web 和邮件入口仍为原有模式 1～3。

也可直接运行：

```bash
python agent.py --hot --hot-hours 24
python agent.py --hot-only --hot-hours 72
python agent.py --hot-replay data/hot_topics/<运行目录>/posts.json
```

`--hot-only` 不调用模型，适合检查采集与排序。`--hot-replay` 从原始素材重新总结，不登录树洞、不重新抓取；保留原统计窗口和排名参数，使用当前模型与生成预算，生成新的运行目录。可结合 `--hot-only` 重新导出素材。重放需要本项目生成的 `schema_version=1` JSON，不接受任意树洞 API 响应。

## 结果与状态

每次运行在 `HOT_OUTPUT_DIR` 下生成唯一目录，默认 `data/hot_topics/`：

- `posts.json`：入选帖原文、评论、父评论关系、原始计数、评分与入选理由、热词、配置、采集完整性。
- `sources.md`：可阅读的原文与评分，长文不截断。
- `summary.md`：模型总结或明确的失败/仅导出说明。

状态 `completed` 表示模型生成并通过格式化出处校验，**不代表全站无遗漏或观点已事实核实**。`partial_summary` 表示模型只读取了预算内的素材块。`exported` 表示仅导出，`summary_failed` 表示模型请求、输出完整性、引用或预算校验失败；素材仍可重放。`no_data` 表示枚举完没有有效素材，`collection_failed` 表示未能采集到可用素材且枚举未完成。命令行后两种失败状态中 `summary_failed`、`collection_failed` 返回退出码 1；正常结束为 0，中断为 130。

## 采集边界

默认扫描最多 5000 条返回记录、200 页，按 ID 去重，固定运行开始时的时间窗口。新插入帖子可能导致页码偏移；这不是服务端一致性快照。扫描上限触发时不冒充完整 24 小时。置顶旧帖不会令程序立即停止；只有已观测的非置顶时间序列持续倒序，且连续两页全部早于窗口时，才按观测边界停止。乱序时继续到空页或上限。报告区分这种观测边界与空页枚举完成。更长窗口可能需要增加扫描上限。

实际接口的 `data.total` 会随着页码变化，例如 30 条/页时第一页 31、第二页 61；它作为诊断值保留，不当作固定总数。新模式使用无关键词的 `/chapi/api/v3/hole/list_comments` 和 `/chapi/api/v3/comment/list`，不使用旧搜索的 24 小时缓存。

请求设连接超时 10 秒、读超时 60 秒、默认间隔 1 秒；网络错误、429 和 5xx 至多尝试 3 次并指数退避，业务认证错误立即报告。DeepSeek 流式读超时沿用 120 秒：这是单次网络读取超时，**不是整次任务总时限**；采集和分块模型调用累计可能需要数分钟。

## 算法与调参

1. Jieba 中文分词，统一英文大小写、过滤 URL/常见停用词，校园词典在 `hot_topics/campus_words.txt`，停用词在 `hot_topics/stopwords.txt`。
2. DF 统计不同帖子中的词语出现次数；一帖重复某词不增加 DF。默认至少 3 帖，显示前 50 个词。全局热词只统计主帖正文，评论在入选后用于讨论总结。
3. 话题分为该帖最多 5 个热词的 DF 之和，除以样本前 5 热词 DF 之和；TF-IDF/余弦用于辅助分组，不直接当热度。组内比较代表帖，避免相似度链式串联所有帖子。分组是模型参考，不强制等同最终话题。
4. 互动指标：收藏 `likenum`、点赞 `praise_num`、评论 `reply`（`comment_total` 经真实联调确认同样是预览分页提示，不作为评论计数）。缺失记 null，不当成零。`praise_num_show` 不作为第二个独立点赞信号。
5. 各指标以正数样本中平均秩计算百分位；零值分数为 0。达到前 10% 且至少收藏 5/点赞 3/评论 10 则独立召回。并列值使用平均名次，因此大量并列时可能没有高互动代表。阈值可调，不是经过大规模评测的最优值。
6. 综合分 `0.4×话题分 + 0.5×互动分 + 0.1×新鲜度`。互动分默认收藏 0.4/点赞 0.3/评论 0.3；按每帖可用指标重分配权重。新鲜度在窗口内线性衰减。关键词与互动候选取并集，先为各互动通道保留一个代表帖，其余按综合分补齐。未达门槛的填充帖明确标注“补充样本”，不称作已判定热点。

例如在 `config_private.py` 中只增加需要调整的项目：

```python
HOT_MAX_SCAN_POSTS = 10000
HOT_MAX_SCAN_PAGES = 400
HOT_MIN_KEYWORD_POSTS = 4
HOT_MIN_FAVORITES = 8
HOT_CONTEXT_CHARS = 24000
HOT_MAX_SUMMARY_CHUNKS = 40
```

其余默认值见 `config_example.py`。不需要重写旧配置。图像/OCR、词语历史爆发、老帖热度增量不在本版范围内。

## 评论与模型上下文

对入选帖从第一页刷新评论，直到空页、重复页、请求失败或评论页数上限；按 `cid` 去重。`comment_id` 关联同帖父评论；父节点未返回时使用同帖且 ID 匹配的 `quote`；否则明确 `missing`。没有父 ID 的发言标为关系未知，不从昵称猜具体回复，也不跨帖识别人。同昵称多条发言不会串联，缺失父评论不推断删除原因。引用对象仅出现在 `quote` 时标为 `quoted_only`。

页面声明数量、接口提示数量与实际抓取数量分别记录。差异不一定代表失败或删除。请求失败时保留已抓评论和列表预览，明确失败页；分页成功时以评论接口为准。原文中保留完整评论，模型输入以来源 ID 标记分片，超长评论尾部仍在后续片段。回复关系和引用文本一并进入素材。

模型先做有出处的分块笔记，再汇总为目标 1500 字以内的报告；不足一个块时直接总结。笔记和最终报告都检查出处 ID 是否存在于结构化来源，并要求至少一个有效出处。格式、ID 校验失败或输出长度截断时最多纠正/压缩一次，仍不通过则报告失败；被拒草稿仅保存在本地 JSON 的 rejected_drafts，不能当作正式总结。纠正请求也计入最多 HOT_MAX_SUMMARY_CHUNKS+1 次总调用预算。该检查不能证明每一句话的语义得到原文支持，仍须人工抽查。超过素材块预算时标明模型覆盖比例；压缩仍超预算则明确失败，不能静默截断成完整报告。流式中断、空输出和长度截断不算成功。

模式 4 对官方 `api.deepseek.com` 默认传入 `thinking={"type":"disabled"}`，避免思考模式先耗尽现有 `MAX_RESPONSE_TOKENS`。模型名称、密钥及输出上限沿用已有配置，模式 1～3 不受影响。依据 [DeepSeek 思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)。可在私有配置设置 `HOT_THINKING="enabled"` 开启（同时考虑提高输出上限），或 `HOT_THINKING=None` 使用服务端默认值。自定义 API 地址默认不发送这个供应商专用参数。


## 验收与调试

离线测试不需要登录或真实模型请求：

```bash
python -m unittest discover -s tests -v
python -m compileall -q agent.py client.py hot_topics tests
```

建议人工验收步骤：

1. 菜单中选择 `4`，默认 24 小时，确认导出最多 30 帖；选 `72`/`168` 时检查窗口起止时间。
2. 打开 `sources.md` 和 `posts.json`，抽查至少 10 帖的时间、收藏/点赞/评论计数、入选理由。计数会变化，应比较接近采集时刻的响应。
3. 找一个多层回复，核对父 `cid` 和引用正文；找一个缺失父节点，确认没有编造发言。
4. 查看扫描停止原因、页数、实际时间覆盖与评论差异；达到上限时确认报告写明“部分覆盖”。
5. 看 `summary.md`：每个话题都应有概述和出处，不重复凑数，不把猜测当事实。确认评论中的纠正/限定没有被忽略。
6. 用 `--hot-only` 分离采集问题，再用 `--hot-replay` 分离模型问题；原导出应保留，新结果写入新目录。
7. 分别运行旧模式 1～3，确认仍能检索、问答和课程测评。

排错定位：列表无数据检查 `scan.stop_reason`/`failed_page`；评论不完整检查每帖 `comment_fetch`；排名不理想检查 `keywords`、`metrics`、`scores`、`selection.reasons`；总结失败检查 `status`/`summary_error_code`（如 `invalid_citations`、`reduction_budget`、`output_token_limit`、`model_request_failed`），随后检查本地模型配置和上下文预算再重放。

本地真实数据与配置被 gitignore 排除；测试仅提交人工合成文本。只有用户完成本地验收后才向 fork 提交 PR 并合并，原项目 PR 由用户发起。
