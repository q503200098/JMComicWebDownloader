FROM python:3.12-slim

# 安装 Pillow（智能封面需要）及其系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo \
    zlib1g \
    libpng16-16 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    flask \
    jmcomic==2.7.2 \
    Pillow

WORKDIR /app

COPY app.py /app/
COPY paths.py /app/
COPY scripts /app/scripts/

# config.yml 由 paths.get_config_path() 运行时动态生成，无需打包
# 数据目录 /app 可挂载持久化，下载目录 /downloads 由用户映射外挂卷
RUN mkdir /downloads

EXPOSE 8080

CMD ["python","app.py"]
