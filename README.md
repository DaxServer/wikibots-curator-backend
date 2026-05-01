![GitHub License](https://img.shields.io/github/license/DaxServer/wikibots-curator-backend?link=https%3A%2F%2Fopensource.org%2Flicense%2FMIT)

# Curator Application

A full-stack application for managing CuratorBot jobs that upload media to Wikimedia Commons.

## Overview

The Curator Application consists of:

1. **Backend**: A FastAPI service with a REST API and WebSocket endpoint. Celery workers handle background upload tasks.
2. **Frontend**: A Vue.js application with TypeScript and PrimeVue for managing uploads and monitoring job status.

## Deployment

### Build

```bash
toolforge build start -i web https://github.com/DaxServer/wikibots-curator-backend.git -L
```

`-L` flag uses the latest buildpacks and base image, required for Poetry.

### Environment variables

Use `toolforge envvars` to set them up. The OAuth1 application is at [OAuth applications - Wikimedia Meta-Wiki](https://meta.wikimedia.org/wiki/Special:OAuthListConsumers/view/8e7c7bbe93a2623af57eb03f37448b3c).

```bash
X_USERNAME
X_API_KEY
CURATOR_OAUTH1_KEY
CURATOR_OAUTH1_SECRET
SESSION_SECRET_KEY
TOKEN_ENCRYPTION_KEY
MAPILLARY_API_TOKEN
WCQS_OAUTH_TOKEN
```

`SESSION_SECRET_KEY` signs cookie sessions. Rotating it invalidates all active user sessions. Generate with:

```bash
openssl rand -hex 32
```

`TOKEN_ENCRYPTION_KEY` encrypts OAuth access tokens stored in the database using Fernet. Must be a valid Fernet key — generate with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Webservice

When deploying for the first time, use:

```bash
toolforge webservice buildservice start --buildservice-image tool-curator/web:latest --mount all
```

For subsequent deployments:

```bash
toolforge webservice restart
```

### Worker

After building the `web` image, run the worker process:

```bash
toolforge jobs run --image tool-curator/web:latest --emails all --continuous --filelog --mount all --command "worker" worker
```

## Development

### Prerequisites

- Python 3.13 or higher
- Poetry (for dependency management)

### Installation

```bash
poetry install
```

### Running the server

```bash
X_USERNAME=DaxServer X_API_KEY=test CURATOR_OAUTH1_KEY=abc123 CURATOR_OAUTH1_SECRET=abc123 SESSION_SECRET_KEY=dev-secret TOKEN_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") poetry run web
```

The backend server will be available at http://localhost:8000.

### Running Tests

```bash
poetry run pytest -q
```

### Code Style

```bash
poetry run isort . && poetry run ruff format && poetry run ruff check
```

### Type Checking

```bash
poetry run ty check
```

## License

[MIT](./LICENSE)
