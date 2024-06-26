# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Install CMake and other necessary build tools
RUN apt-get update && \
    apt-get install -y cmake g++ && \
    apt-get clean

# Set the working directory in the container
WORKDIR /usr/src/app

# Set PYTHONPATH
ENV PYTHONPATH="${PYTHONPATH}:/usr/src/app"

# Copy the current directory contents into the container
COPY . .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run app.py when the container launches
CMD ["python", "app/__init__.py"]