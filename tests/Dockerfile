FROM python:3.11-slim

WORKDIR /app

# Install test dependencies from the root requirements file
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire tests directory into the image
COPY tests/ tests/

CMD ["python", "-m", "pytest", "tests/", "-v", "--tb=short"]
