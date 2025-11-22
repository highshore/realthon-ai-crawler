FROM public.ecr.aws/lambda/python:3.11

WORKDIR ${LAMBDA_TASK_ROOT}

RUN yum install -y \
    alsa-lib \
    atk \
    at-spi2-atk \
    at-spi2-core \
    curl \
    cups-libs \
    dbus-glib \
    glib2 \
    gtk3 \
    libdrm \
    libX11 \
    libXcomposite \
    libXcursor \
    libXdamage \
    libXext \
    libXi \
    libXfixes \
    libXrandr \
    libXrender \
    libXScrnSaver \
    libXtst \
    libxcb \
    libxkbcommon \
    mesa-libEGL \
    mesa-libgbm \
    nss \
    pango \
    unzip \
    xorg-x11-server-Xvfb \
 && yum clean all

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

ENV CHROME_VERSION=126.0.6478.182
RUN curl -sSL https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip -o /tmp/chrome.zip \
    && unzip /tmp/chrome.zip -d /opt/ \
    && mv /opt/chrome-linux64 /opt/chrome \
    && rm /tmp/chrome.zip

RUN curl -sSL https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chromedriver-linux64.zip -o /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /opt/ \
    && mv /opt/chromedriver-linux64/chromedriver /opt/chromedriver \
    && chmod +x /opt/chromedriver \
    && rm -rf /opt/chromedriver-linux64 /tmp/chromedriver.zip

ENV LINKAREER_BROWSER_PATH=/opt/chrome/chrome
ENV LINKAREER_CHROMEDRIVER_PATH=/opt/chromedriver

COPY app ./app

CMD ["app.router.lambda_handler"]