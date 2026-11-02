
FROM python:3.13-slim-bookworm

WORKDIR /app

# Dependencias del sistema y controlador ODBC de Microsoft
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    gnupg \
    unixodbc \
    unixodbc-dev \
    libgssapi-krb5-2 \
    && curl -sSL -O https://packages.microsoft.com/config/debian/12/packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && rm -rf /var/lib/apt/lists/*

# Instalar las librerías de Python necesarias
RUN pip install --no-cache-dir Flask==3.1.1 pyodbc==5.3.0

# Copiar la aplicación
COPY . .

EXPOSE 5000

CMD ["python", "-c", "from app import app; app.run(host='0.0.0.0', port=5000, debug=False)"]
