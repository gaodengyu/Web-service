GameBuddy
=========

GameBuddy 是一个基于 Flask 的电竞陪玩 / 陪练 / 代练预约平台 MVP。

核心能力：
- 玩家搜索与筛选
- 结构化下单与 Stripe 支付
- 履约、确认完成、评价、投诉
- 站内聊天与通知
- 管理后台（订单、投诉、用户治理）

运行方式
--------
1) 安装依赖
	pip install -r requirements.txt

2) 可选创建 .env（建议至少配置）
	SECRET_KEY=replace_with_a_random_secret
	ADMIN_REGISTER_PASSWORD=your_admin_create_password

3) 启动
	python app.py

4) 打开
	http://localhost:5000

支付说明
--------
- 仅支持 Stripe Checkout（已移除演示支付）
- 必须配置 STRIPE_SECRET_KEY（sk_ 开头）
- 未配置时会直接报错提示配置问题

数据库说明
----------
- 默认 SQLite：data.db
- 配置 DATABASE_URL 可切换 PostgreSQL
- PostgreSQL 不可用时会快速回退 SQLite

关键环境变量（新增）
------------------
1) ALLOW_DOTENV_DATABASE_URL
	- 默认 false
	- 默认不从 .env 自动加载 DATABASE_URL
	- 需要从 .env 启用远端库时设置为 1/true

2) APP_BOOTSTRAP_ON_IMPORT
	- 默认 false
	- 默认不在 import app 时执行初始化/迁移/种子
	- python app.py 启动时仍会执行完整 bootstrap
	- 仅在需要“导入即初始化”时设置为 1/true
