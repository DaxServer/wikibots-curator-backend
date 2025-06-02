![GitHub License](https://img.shields.io/github/license/DaxServer/wikibots-curator-backend?link=https%3A%2F%2Fopensource.org%2Flicense%2FMIT)

# Curator Application

A full-stack application for managing and monitoring CuratorBot jobs.

## Overview

The Curator Application consists of:

1. **Backend**: A FastAPI-based service that provides an interface to the Wikimedia Toolforge API
2. **Frontend**: A Vue.js application with TypeScript and PrimeVue for displaying and managing Toolforge jobs

This application is designed to work within the Wikimedia ecosystem, particularly for tools that need to interact with the Toolforge infrastructure programmatically.

## Deployment

### Build

```bash
toolforge build start -i web https://github.com/DaxServer/wikibots-curator-backend.git -L
```

`-L` flag uses the latest buildpacks and base image, required for Poetry.

### Environment Variables

Use `toolforge envvars` to set them up. The OAuth1 application is at [OAuth applications - Wikimedia Meta-Wiki](https://meta.wikimedia.org/wiki/Special:OAuthListConsumers/view/8e7c7bbe93a2623af57eb03f37448b3c).

```bash
X_USERNAME
OAUTH_CLIENT_SECRET
OAUTH_CLIENT_ID
SECRET_KEY
```

When deploying for the first time, use:

```bash
toolforge webservice buildservice start --buildservice-image tool-curator/web:latest --mount all
```

For subsequent deployments, use:
```bash
toolforge webservice restart
```

## Development

This project is the Backend application.

### Prerequisites

- Python 3.13 or higher
- Poetry (for dependency management)

### Installation

Install backend dependencies:

```bash
poetry install
```

### Running the Server

Start the FastAPI server:

```bash
X_USERNAME=DaxServer OAUTH_CLIENT_ID=abc123 OAUTH_CLIENT_SECRET=abc123 poetry run web
```

The backend server will be available at http://localhost:8000. The OAuth1 application is at [OAuth applications - Wikimedia Meta-Wiki](https://meta.wikimedia.org/wiki/Special:OAuthListConsumers/view/007829f26d944fb553e89e0c0fd02f31).

### Testing build

Build the frontend for production:

```bash
pack build -B tools-harbor.wmcloud.org/toolforge/heroku-builder:24_0.20.7 curator-web
```

### Running Tests

To run the tests, use the following command:

```bash
poetry run pytest
```

For verbose output:

```bash
poetry run pytest -v
```

## License

[MIT](./LICENSE)
