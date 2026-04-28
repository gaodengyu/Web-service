# GameBuddy

GameBuddy 是一个基于 Flask 的电竞陪玩 / 陪练 / 代练预约平台 MVP，围绕课程 proposal 中的核心闭环完成了以下能力：

- 玩家搜索与筛选打手
- 结构化下单与 Stripe 支付
- 打手接单、履约、标记完成
- 玩家确认完成、评分、投诉
- 站内聊天与自动通知
- 管理员统计面板、订单筛选、投诉处理、退款标记、用户治理

## 运行方式

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 可选：创建 `.env`

参考 `.env.example`，至少建议配置：

```env
SECRET_KEY=replace_with_a_random_secret
ADMIN_REGISTER_PASSWORD=your_admin_create_password
```

3. 启动项目

```bash
python app.py
```

4. 打开浏览器

```text
http://localhost:5000
```

## Service System（前后端分离）

项目现在同时保留了原有 Flask 模板页面，以及一套独立的 `Service System`：

- Frontend Shell: `/service`
- JSON API: `/api/*`
- Database Read/Write Layer: `service_system/database.py` + `service_system/actions.py`

新的分层入口如下：

- `service_system/frontend.py`
	- 负责挂载前端壳页面，让浏览器加载 `static/service-system/app.js` 和 `styles.css`
- `service_system/api.py`
	- 负责挂载 `/api/bootstrap`、`/api/stores`、`/api/dashboard`、`/api/orders` 等服务接口
- `service_system/database.py`
	- 负责构造面向前端消费的数据快照（discovery、dashboard、orders、wallet、chat、admin）
- `service_system/actions.py`
	- 负责审核、申诉处理、管理员动作等写操作
- `service_system/serializers.py`
	- 负责把数据库/领域对象序列化为前端可直接消费的 JSON

如果你要验收“前后端分离”的版本，直接访问：

```text
http://localhost:5000/service
```

这时浏览器界面由 `static/service-system/app.js` 驱动，页面数据通过 `/api/*` 拉取，不再依赖服务端模板渲染业务视图。

## 支付说明

- 仅支持 Stripe Checkout 支付（已移除演示支付模式）。
- 必须配置 `STRIPE_SECRET_KEY`（`sk_` 开头），否则下单会直接报错并提示配置问题。

## 数据库说明

- 默认使用本地 SQLite：`data.db`
- 如果配置 `DATABASE_URL`，会自动切换到 PostgreSQL
- 当 PostgreSQL 暂时不可用时，会快速回退到 SQLite，避免启动长时间卡死
- 项目启动时会补齐新字段，并迁移 `users.json` / `orders.json` 中的初始数据

## 关键环境变量（新增）

- `ALLOW_DOTENV_DATABASE_URL`
	- 默认：未设置（等价于 `false`）
	- 行为：默认不从 `.env` 自动加载 `DATABASE_URL`，避免开发机误连远端数据库
	- 需要从 `.env` 启用远端库时，显式设置为 `1` / `true`

- `APP_BOOTSTRAP_ON_IMPORT`
	- 默认：未设置（等价于 `false`）
	- 行为：默认不在 `import app` 时执行初始化/迁移/种子流程（测试与脚本更稳定）
	- `python app.py` 启动时仍会执行完整 bootstrap
	- 仅在你明确需要“导入即初始化”时设置为 `1` / `true`

## 当前 MVP 对应 Proposal 的实现重点

- 搜索 / 匹配：支持按游戏、段位、价格、时间筛选，并结合评分 / 完成单量 / 当前负载排序
- 订单闭环：下单 -> 待接单 -> 已接单 -> 待确认完成 -> 已完成
- 投诉处理：玩家提交投诉，管理员更新投诉状态并反馈处理结果
- 自动通知：下单、接单、完成、投诉、处理结果都会写入站内通知
- 管理后台：查看核心指标、用户管理、订单筛选、投诉与退款处理

## 课程答辩建议演示路线

1. 用玩家账号登录，进入“找打手”页面做筛选并创建订单
2. 切换打手账号，演示接单与完成服务
3. 切回玩家账号，确认完成、评分并提交投诉
4. 切换管理员账号，展示统计面板与投诉处理流程
5. 最后进入聊天与通知页面，展示事件联动
