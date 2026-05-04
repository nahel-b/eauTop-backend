FROM node:18-bullseye-slim

# Set working directory
WORKDIR /app

# Copy package.json and package-lock.json first for efficient caching
COPY package*.json ./

# Install Python and pip before npm ci so postinstall can use them if needed
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

# Install Node.js dependencies
RUN npm ci

# Copy only the Python requirements file needed for dependency installation
COPY volume-estimation/requirements-inference.txt ./volume-estimation/requirements-inference.txt

# Install Python dependencies required by volume-estimation
RUN python3 -m pip install --no-cache-dir -r volume-estimation/requirements-inference.txt

# Copy the rest of the application files
COPY . .

# Expose the port expected by the app
EXPOSE 5000

# Start the Node.js app
CMD ["npm", "start"]
