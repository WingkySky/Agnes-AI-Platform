# 部署指南

本文覆盖 Docker 部署的完整流程：本地快速跑通、公网服务器部署（反向代理 / HTTPS）、数据备份与升级。

## 快速开始（本地 / NAS）

```bash
# 方式一：docker run
docker run -d --name agnes-platform -p 8080:8000 -v agnes-data:/app/data ghcr.io/wingkysky/agnes-ai-platform:latest

# 方式二：docker compose（克隆仓库后，在仓库根目录执行）
docker compose up -d
```

访问 `http://localhost:8080`，按首启向导完成管理员密码与 AI 服务配置即可使用。

## 数据卷说明

所有持久化数据都在 `agnes-data` 卷（容器内 `/app/data`）：

| 卷内路径 | 内容 |
|---|---|
| `agnes_platform.db` | SQLite 数据库（用户、Provider、作品、画布等全部业务数据） |
| `uploads/` | 用户上传的素材、头像、水印图片 |
| `appdata/` | MCP 记忆图谱、流水线输出等运行时数据 |
| `logs/` | 后端日志 |
| `secrets.env` | 自动生成的 JWT_SECRET / ENCRYPTION_KEY |

密钥在首次启动时自动生成并写入 `secrets.env`，升级镜像不会变化——这意味着已登录用户和已加密保存的 Provider API Key 在升级后依然有效。也可以用环境变量 `JWT_SECRET` / `ENCRYPTION_KEY` 显式注入（优先级高于 `secrets.env`）。

## 端口与时区

- 容器内监听 8000，通过 `-p 8080:8000` 自定义宿主端口
- 容器默认 UTC 时区，影响日志时间戳；如需本地时区：`-e TZ=Asia/Shanghai`（compose 文件中有注释示例）

## 公网服务器部署（反向代理 + HTTPS）

生产建议在 nginx / Caddy 后面运行，由代理层负责 HTTPS。

### nginx 示例

```nginx
server {
    listen 443 ssl;
    server_name agnes.example.com;
    # ssl_certificate / ssl_certificate_key 按需配置

    # 上传素材（图片 / 视频）较大时放开限制
    client_max_body_size 100m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # AI 对话为 SSE 流式响应，必须关缓冲，否则输出会卡顿/整段延迟
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

### Caddy 示例（自动 HTTPS）

```caddy
agnes.example.com {
    reverse_proxy 127.0.0.1:8080 {
        flush_interval -1
    }
    request_body {
        max_size 100MB
    }
}
```

## 数据备份

数据全在卷里，备份即打包卷：

```bash
# 备份（应用运行中也可执行，SQLite 一致性以短停机更稳妥）
docker run --rm -v agnes-data:/data -v $(pwd):/backup alpine \
    tar czf /backup/agnes-data-$(date +%F).tar.gz -C /data .

# 恢复
docker run --rm -v agnes-data:/data -v $(pwd):/backup alpine \
    tar xzf /backup/agnes-data-*.tar.gz -C /data
```

## 升级

```bash
docker compose pull          # 或 docker pull ghcr.io/wingkysky/agnes-ai-platform:latest
docker compose up -d         # 重建容器，数据卷原样保留
```

数据库建表与种子数据由应用启动时自动完成（幂等），升级无需手动迁移步骤。

## 可选：PostgreSQL

自托管场景默认 SQLite 已足够；多用户服务器场景如需 PostgreSQL，取消 `docker-compose.yml` 中注释掉的 `db` 服务与 `DATABASE_URL` 配置即可，后端原生支持，无需其他改动。

## 常见问题

- **拉取镜像慢 / 失败**：GHCR 在部分地区网络不稳定，可配置 Docker 镜像加速或使用代理拉取。
- **上传大视频失败**：反代场景检查 `client_max_body_size`（nginx）或 `max_size`（Caddy）。
- **对话输出卡顿**：反代未关缓冲，确认 `proxy_buffering off`（nginx）或 `flush_interval -1`（Caddy）。
