FROM python:3.14.3-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install OS dependencies and Node.js 20.19.4
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
    git \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libx11-6 \
    libxcb1 \
  && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://nodejs.org/dist/v20.19.4/node-v20.19.4-linux-x64.tar.xz -o /tmp/node.tar.xz \
  && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
  && rm /tmp/node.tar.xz

# Copy Node app files first for caching
COPY package*.json ./
RUN npm ci

# Copy Python requirement file and install exact local Python dependencies
COPY volume-estimation/requirements.txt ./volume-estimation/requirements.txt
RUN python3 -m pip install --upgrade pip setuptools wheel \
  && python3 -m pip install --no-cache-dir -r volume-estimation/requirements.txt -f https://download.pytorch.org/whl/cpu/torch_stable.html

# Copy the rest of the project
COPY . .

EXPOSE 5000
CMD ["npm", "start"]
