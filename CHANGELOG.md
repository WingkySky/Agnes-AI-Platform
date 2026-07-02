# Changelog

本文件记录 Agnes AI Platform 的所有版本变更。格式参考 [Keep a Changelog](https://keepachangelog.com/)。

## [Unreleased]

### 安全
- 移除 `jwt_secret` 不安全默认值，启动时强制校验非空、非默认占位值、长度≥32 字节
- 移除 `encryption_key` 默认空兜底，启动时强制校验非空；`security._derive_key` 不再使用内置默认密钥
- 补全 `.env.example` 缺失变量（JWT_SECRET / SMTP_* / CAPTCHA_* / EMAIL_CODE_* / BACKEND_PORT / LOG_* / NEW_USER_DEFAULT_CREDITS）
- 默认 admin 账号与首位注册管理员 `must_change_password=True`，登录响应与 `/auth/me` 返回该标志；新增 `POST /auth/change-password` 接口（旧密码+新密码），修改成功后清除标志；邮箱重置密码后自动清除标志
- S5（/uploads 鉴权代理）经审查后跳过：avatars 目录受广场匿名浏览硬约束必须公开，watermarked 目录因水印下载接口动态处理未被使用，当前无真正需要鉴权的上传文件

### 性能
- 修复 `system_config_service.get_config_value` 缓存永不过期 bug（增加 60 秒 TTL 检查）
- `moderation_service.check_sensitive_text` 添加进程内 60 秒 TTL 缓存，敏感词增删改后自动清除
- `credits_service._get_rule_value` 添加进程内 60 秒 TTL 缓存，积分规则修改/重置后自动清除

### 可观测性
- `admin_review` 统一审核接口的 9 处静默 `except: pass` 改为 `logger.exception`，保留默认 0 值不破坏前端逻辑

### 工程化
- 建立 `VERSION` 文件（0.0.1）与 `CHANGELOG.md`
- 从 `.gitignore` 移除 `docs/`，设计文档纳入版本控制
