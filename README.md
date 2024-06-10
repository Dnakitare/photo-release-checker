# Photo Release Checker

Photo Release Checker is a Flask web application that helps the social media director for a summer camp to identify photographs containing individuals who have not signed a photo release. The application uses facial recognition to scan photos and flag those that contain known faces without a release.

## Features

- User authentication with registration and login
- Upload known faces for identification
- Upload photos to scan for known faces
- Display results of scanned photos with identified faces
- Session-specific directories for user uploads
- Dockerized setup for easy deployment
- Database initialization using Flask-Migrate

## Prerequisites

- Docker
- Docker Compose

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/dnakitare/photo-release-checker.git
    cd photo-release-checker
    ```

2. Create a `.env` file in the root directory and add your secret key:
    ```env
    SECRET_KEY=your_secret_key
    ```

3. Build and run the Docker containers:
    ```bash
    docker-compose up --build
    ```

4. The application will be available at `http://localhost:5001`.

## Usage

1. Open a web browser and navigate to `http://localhost:5001`.

2. Register a new user or log in with existing credentials.

3. Upload images of known faces that should not appear in the photos for release.

4. Upload photos to scan for known faces.

5. View the results of the scan, which will indicate if any known faces are present in the uploaded photos.

## Development

### Initializing the Database

The database is automatically initialized and migrated when the Docker container is started. If you need to manually run the migrations, you can use the following commands:

1. Access the Docker container:
    ```bash
    docker-compose exec web /bin/sh
    ```

2. Run the Flask-Migrate commands:
    ```bash
    flask db init
    flask db migrate -m "Initial migration."
    flask db upgrade
    ```
## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any changes.

## License

This project is licensed under the Apache 2.0 License. See the `LICENSE` file for details.