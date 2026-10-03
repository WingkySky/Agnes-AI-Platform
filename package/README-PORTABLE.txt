Agnes AI Platform 便携版（免安装）
====================================

一、启动
------------------------------------
Windows：双击 start-windows.bat
  - 首次运行如遇 SmartScreen 蓝色提示（未签名应用的正常现象），
    点「更多信息」->「仍要运行」即可。

macOS（Apple Silicon）：双击 start-macos.command
  - 首次运行先打开「终端」，依次执行下面两行命令
    （把目录换成你实际解压的路径）：
      xattr -cr ~/Downloads/agnes-platform
      chmod +x ~/Downloads/agnes-platform/start-macos.command
  - 之后双击 start-macos.command 即可，浏览器会自动打开。
  - 若双击仍提示「没有正确的访问权限」，重新执行上面第二行 chmod 命令。
  - 仅支持 Apple Silicon（M1 及以后）；Intel Mac 请用 Docker 或源码运行。

启动后浏览器自动打开 http://localhost:8000 ，
按首启向导完成管理员密码与 AI 服务配置即可使用。

二、数据在哪
------------------------------------
所有数据都在本文件夹内，备份 = 复制文件夹：
  backend/agnes_platform.db   数据库（用户、作品、画布等）
  backend/uploads/            上传的素材
  backend/logs/               日志
  backend/.env                配置与自动生成的安全密钥（勿外传）

三、升级
------------------------------------
下载新版本便携包解压，把旧文件夹 backend/ 整个拷进新文件夹覆盖即可
（保留数据库、素材与密钥）。

四、常见问题
------------------------------------
- 端口被占用：启动时会自动探测并顺延到下一个空闲端口
  （如开发服务已占用 8000，包会自动改用 8001），终端窗口
  会显示实际端口，浏览器也会自动打开正确地址。不同端口
  的数据完全独立。
- 想局域网访问：本服务已监听 0.0.0.0，同一局域网设备访问
  http://<你的IP>:<端口> 即可。
- MCP / TTS 等功能开箱即用；MCP 市场安装本地服务器类条目需另装 Node.js。
