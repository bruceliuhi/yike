# 原生搜索页内进度与持久接续

完整V0.2继续；本批先贯通B站search的实际搜索页内进度，不将公共round或记录数伪装成平台cursor。小红书、抖音、知乎和评论深翻仍在后续范围，不宣称本批完成所有平台。

## 取舍

- 页码直接加一会漏掉一页中未处理的内容，不能采用。
- 只留本地marker会在上传失败/换设备时与服务端事实分离，不能作为下轮权威。
- 采用真实搜索页＋页内已处理aid，CLAIM固定快照，签名batch原文和进度短事务共提交。每次来源停止成功才产生tentative输出，未上传不生效；UNKNOWN只恢复原请求。

本批cursor的含义是“搜索结果条目及其有界评论样本”，**不是完整评论树读取进度**。每条进度明确`comments_scope:BOUNDED_SAMPLE`，旧条目的评论深翻另接，不以搜索页推进宣称评论已穷尽。主帖/评论证据语义、候选条数和FINISH不改变。

## 固定协议

适配器`bili-search-items-v1`；schema `native-search-progress-v1`；仅BILIBILI/PLATFORM_ACCOUNT/已确认monitor/search允许。真实账号仍必须同浏览器校验。无协商、单次和links保持旧路径。

Cursor精确字段：`{page:1..1000, consumed_ids:aid字符串数组(ASCII正整数字符串,每项<=20位,唯一,最多20), refresh_next:boolean}`。初值page1/[]/false。每query另带`revision:0..2147483647`和`base_batch_request_id:null|既有opaque`；revision0当且仅当base为null。

- CLAIM请求可选`native_progress_version:1`，仅精确整数1，和public_sampling_version互斥，旧缺省不添null/undefined。
- CLAIM回执可选`native_progress:{schema_version,adapter_version,plan_id,queries:[{query,revision,base_batch_request_id,cursor}]}`。queries为冻结平台关键词原序列；每query最多80字符，查询范围不由用户另行提供。RENEW不带此字段，重放CLAIM固定原值。
- batch可选`native_progress:{schema_version,adapter_version,claim_request_id,queries:[{query,revision,base_batch_request_id,before,after,page_ids,processed_ids,has_more,comments_scope}]}`；revision和base是CLAIM中的值；before/after均Cursor；page_ids是本次真实页全部aid（唯一最多20）；processed_ids是本次完成详情及有界评论读取的aid（唯一最多5、不得超本query输出分配所对应内容预算）。未处理query不提交项；提交数组至少1项，不重复query。
- batch receipt原样回显native_progress，严格对照原请求；缺省旧合同/签名/fingerprint/回执不增字段。进度被签名但仍是设备声明，不能当平台独立证明。
- 私有`execution.support {progressVersion:1}`映射`GET /api/ui/execution-support?native_progress_version=1`；新服务仅在已有B站monitor policy下额外广告`native_progress:["BILIBILI"]`，旧服务无广告保留旧行为。公开sampling_version=1协商不变，不允许混合/重复/多余query。客户端仅B站search monitor询问。

## 页内推进与刷新

每query仅发一次search page请求，固定page_size=20；由真实响应`numPages`（非负int）及result列表校验has_more。非空页面必须page<=numPages；空页只可在明确无更多页时结束。异常/验证码/限流不转成空成功。

`refresh_next=true`时读page1，忽略续读页内IDs，取前min(5,分配内容预算)项；成功后仅把refresh_next翻false，续读page/IDs不变。

否则读cursor.page，按返回顺序取不在consumed_ids中的前min(5,分配内容预算)项。成功处理并获得有界评论样本后，`consumed=page_ids中属于原consumed_ids或processed_ids的项`。若整页均已处理，则page+1/[]；无更多页或达到1000页边界则重置page1/[]。否则保持page/consumed。最后refresh_next=true。页内0新项允许推进，但不能发额外search补满。

`processed_ids`必须等于可选项的有界前缀，不能包含不在page_ids的ID或在CONTINUE中重复消费；非空可选项时至少处理1项。before/after必须符合上述纯函数重算；REFRESH也验证page1样本。动态索引重排仍可能重复或漏项，不声称快照一致；交替刷新保证深翻时仍定期看前部。

## 持久化与执行

新增专用`pilot_native_search_progress` head表，按tenant/owner/plan/profile/strategy/platform/connection_id/version/adapter/query绑定，持久cursor、revision和head batch id。沿既有runtime grants与RLS，应用只在既有批次事务中更新；无浏览器/模型网络长事务。

CLAIM从实际task/occurrence/plan和冻结connection查询head，不改变head。batch入库锁现有execution，再对同scope head串行锁并CAS检查revision/base/before等于CLAIM且当前head未推进。写原文和不可变batch、更新head后执行原最终fence，同事务回滚。空batch照常写进度；同请求重放返回原回执，不双推进。账户/连接version/策略变化初始新scope，不复用旧账号的搜索进度。

正式客户端controller→worker→Python driver→host→受控平台入口传入每query cursor；平台入口返回真实page_ids/processed_ids/has_more/after。worker仅在新协商时接受`{records,nativeProgress}`，旧driver返回数组不变。候选journal加密保存完整batch，原恢复链复用；不把tentative marker当下轮输入。原native runtime pin/patch/hash校验、可见浏览器、账号隔离、物理停止、总时间/候选预算不放宽。

## 验收

TDD先覆盖前5→后5而非跳第2页、页内已处理项、空页、刷新、部分页、重复/非法ID、评论读取失败不出progress、取消/物理未停止不提交。真实受限PG＋认证HTTP覆盖CLAIM→空/非空batch共提交→下一CLAIM、回滚、并发同head只能一次、原请求恢复、连接/owner隔离、旧字节不变。正式TS解析真实HTTP产物，受控runtime离线响应验证真实函数；不以这些替代Windows/实际平台或客户验收。

根端按2026-09-11既定V0.2自主细化授权执行；一次整批非作者review，同字节验证复用，不在本批部署或重构候选安装包。
