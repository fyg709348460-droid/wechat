# 使用官方 Python 基础镜像
[cite_start][cite: 1] FROM python:3.10-slim

# 1. 设置工作目录
WORKDIR /app

# 2. 安装系统依赖 (Edge-TTS 需要 ffmpeg)
# 加上 --no-install-recommends 减小体积
RUN apt-get update && apt-get install -y ffmpeg --no-install-recommends && rm -rf /var/lib/apt/lists/*

# 3. 复制依赖文件并安装
COPY requirements.txt .
[cite_start][cite: 2] RUN pip install --no-cache-dir -r requirements.txt

# 4. 复制主程序代码
COPY app.py .

# 5. 暴露端口 8080 (Zeabur 默认识别此端口)
EXPOSE 8080

# 6. 启动命令 (让 app.py 里的逻辑去处理端口)
CMD ["python", "app.py"]