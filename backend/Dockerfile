FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y curl gnupg ca-certificates python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

RUN echo "deb https://download.opensuse.org/repositories/home:/t-paul/xUbuntu_22.04/ ./" > /etc/apt/sources.list.d/openscad.list && \
    curl -fsSL https://download.opensuse.org/repositories/home:/t-paul/xUbuntu_22.04/Release.key | gpg --dearmor -o /etc/apt/trusted.gpg.d/openscad.gpg

RUN apt-get update && \
    apt-get install -y openscad && \
    rm -rf /var/lib/apt/lists/*

RUN openscad --version

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

CMD python3 app.py
