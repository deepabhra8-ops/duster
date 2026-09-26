# syntax=docker/dockerfile:1

# Pinned to bookworm (Debian 12), not the floating "slim" tag: Microsoft's
# SQL Server ODBC driver repo below is published per-Debian-release, and
# "python:3.11-slim" has already moved on to Debian 13 (trixie).
FROM python:3.11-slim-bookworm

# PySpark embeds a JVM (Java 17 required). pyodbc needs unixODBC plus the
# Microsoft ODBC Driver 18 for SQL Server, since DATABASE_URL is a
# mssql+pyodbc connection string (see backend/.env.example).
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless unixodbc unixodbc-dev g++ curl gnupg && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb -o /tmp/mssql-repo.deb && dpkg -i /tmp/mssql-repo.deb && rm -f /tmp/mssql-repo.deb

RUN apt-get update && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 && apt-get purge -y --auto-remove curl gnupg && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /usr/sbin/nologin appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# backend/'s contents land in /app/backend (not /app directly), mirroring the
# repo layout where backend/ and runtime/ are siblings: paths_config.py
# derives RUNTIME_DIR from backend's own parent directory, so this keeps
# job/upload storage at /app/runtime instead of spilling out to /.
COPY --chown=appuser:appuser backend/ ./backend/
RUN mkdir -p /app/runtime && chown -R appuser:appuser /app/runtime

USER appuser
WORKDIR /app/backend

EXPOSE 5050

# Run uvicorn directly (not "python app.py") so it binds 0.0.0.0 rather than
# the app's hardcoded 127.0.0.1 default in core/config/server_config.py,
# which wouldn't be reachable from outside the container.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5050"]
