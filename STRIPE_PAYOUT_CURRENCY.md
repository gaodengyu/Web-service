# Stripe 提现币种配置说明

## 1. 如何设置提现币种
- 在 `.env` 文件中添加或修改：
  ```
  STRIPE_PAYOUT_CURRENCY=usd
  ```
- 支持币种如：usd、cny、eur 等，需与 Stripe 后台已绑定的外部账户币种一致。

## 2. Stripe 后台如何绑定外部账户
- 登录 Stripe Dashboard
- 依次进入：设置 > 银行账户和调度 > 添加外部账户
- 绑定支持目标币种（如 USD、CNY）的银行卡/银行账户

## 3. 常见报错与解决办法
- **报错：Sorry, you don't have any external accounts in that currency (usd).**
  - 说明 Stripe 账号未绑定可接收该币种的外部账户。
  - 解决：请在 Stripe 后台绑定对应币种账户，或将 STRIPE_PAYOUT_CURRENCY 改为已绑定币种。
- **报错：currency is not supported**
  - 说明当前币种不被 Stripe 支持。
  - 解决：请检查 STRIPE_PAYOUT_CURRENCY 设置，或在 Stripe 后台确认支持的币种列表。

## 4. 其他建议
- 修改币种配置后，建议重启服务。
- 如遇问题可联系平台管理员协助。
