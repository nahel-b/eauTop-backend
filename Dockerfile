FROM node:18-bullseye-slim

# Set working directory
WORKDIR /app

# Copy package.json and package-lock.json
COPY package*.json ./

# Install Node.js dependencies
RUN npm ci

# Install Python and pip
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip \
  && rm -rf /var/lib/apt/lists/*

# Copy all sources
COPY . .

# Expose the port (change if needed)
EXPOSE 5000

# Start the Node.js app
CMD ["npm", "start"]
