FROM python:3.12-slim
# slim image: much lighter than the default python one

WORKDIR /app

# copy the requirements file in the workdir (build context is the project root)
COPY requirements.txt .

# install the Python requirements
RUN pip install --no-cache-dir -r requirements.txt

# copy the app files and directories
COPY booking/ .

# public key mounted at /keys by docker-compose (only needed to check tokens)
ENV JWT_PUBLIC_KEY_PATH=/keys/public_key.pem

# start booking.py when the container is started
CMD ["python", "booking.py"]
