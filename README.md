# Curator Application

A full-stack application for managing and monitoring Wikimedia Toolforge jobs.

## Overview

The Curator Application consists of:

1. **Backend**: A FastAPI-based service that provides a secure interface to the Wikimedia Toolforge API
2. **Frontend**: A Vue.js application with TypeScript and PrimeVue for displaying and managing Toolforge jobs

This application is designed to work within the Wikimedia ecosystem, particularly for tools that need to interact with the Toolforge infrastructure programmatically.

## Deployment

ToDo

## Development

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
X_API_KEY=abc123 poetry run web
```

The backend server will be available at http://localhost:8000.

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

MIT
