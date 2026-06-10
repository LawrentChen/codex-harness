---
name: ricequant-sdk
description: Ricequant SDK 量化开发指南，覆盖 RQData（rqdatac）数据查询、RQAlpha Plus 策略回测、RQFactor 因子研究、RQOptimizer 组合优化和 RQPAttr 绩效归因。用户提及 Ricequant、米筐、rqsdk、rqdatac、rqalpha、rqfactor、rqoptimizer、rqpattr，或要求使用这些组件编写、修改、排查金融数据查询、量化回测、因子检验、组合优化及绩效归因代码时使用。
---

# Ricequant SDK

## 工作流

1. 根据任务确定组件：
   - `rqdatac`：金融数据、行情、合约、财务、行业、指数成分等查询。
   - RQAlpha Plus：策略生命周期、下单、回测配置和结果分析。
   - RQFactor：因子定义、计算、预处理和检验。
   - RQOptimizer：选股和组合权重优化。
   - RQPAttr：Brinson 或因子绩效归因。
2. 在写代码前打开 [references/document-index.md](references/document-index.md)，定位任务对应的官方文档。
3. 获取并阅读相关官方文档页面。优先使用当前环境提供的网页浏览工具；也可在终端运行 `curl -sL <URL>`。
4. 以当前官方文档为准确认函数名、参数、返回类型和版本差异，不凭记忆补全 API。
5. 检查项目现有代码、依赖版本和本地约定，再按项目风格实现。
6. 执行 `rqdatac` 查询前先调用 `rqdatac.init()`，确认当前 Python 环境已安装 RQSDK 且许可证可用。仅查阅文档或编写不执行的示例时，不要把许可证检查作为阻断条件。
7. 能访问已安装环境时，用 `inspect.signature()`、`help()` 或最小查询验证关键 API；需要账号、网络或付费权限时，不伪造运行结果。

## 实现原则

- 只从 `ricequant.com` 官方文档获取 RQSDK API 事实；搜索结果仅用于定位官方页面。
- 优先复用项目中已有的初始化、配置和数据转换方式。
- 区分 `rqdatac` 的研究数据 API 与 RQAlpha 策略运行时的数据 API，不混用相似函数。
- 明确日期范围、标的代码、频率、字段、复权方式和返回结构。
- 使用标准米筐代码格式，例如 `600000.XSHG`、`000001.XSHE`、`830799.XBSE`。
- API 参数涉及股票、基金、期货或期权合约时，不根据名称臆造代码。按 [references/asset-code-workflow.md](references/asset-code-workflow.md) 查询并验证真实代码。
- 对 DataFrame 结果先确认实际类型是 Pandas、Polars 还是其他结构，再编写索引、连接和导出逻辑。
- 提交代码前按 [references/rqdata-pitfalls.md](references/rqdata-pitfalls.md) 检查常见误用。
- 不确定的 API 行为应继续查官方文档或本地验证；只有业务含义无法从代码和文档判断时才询问用户。

## 本地验证

优先在项目使用的 Python 环境中运行：

```python
import inspect
import rqdatac

rqdatac.init()
print(inspect.signature(rqdatac.get_price))
help(rqdatac.get_price)
```

若 `rqdatac.init()` 失败，应原样说明缺少安装、许可证未配置或许可证不可用等实际错误，并停止执行依赖 RQData 的查询。不要猜测数据，也不要输出或写入账号凭据。

验证时使用最小日期范围和少量标的，避免无意发起大规模数据请求。

## 文档索引维护

官方总索引为：

```text
https://www.ricequant.com/doc/document-index.txt
```

当 [references/document-index.md](references/document-index.md) 缺少所需页面或链接失效时，先读取官方总索引，再使用其中的新链接完成任务并更新本 skill 的索引。
