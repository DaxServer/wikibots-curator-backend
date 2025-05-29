# Curator Application

A full-stack application for managing and monitoring Wikimedia Toolforge jobs.

## Overview

The Curator Application consists of:

1. **Backend**: A FastAPI-based service that provides a secure interface to the Wikimedia Toolforge API
2. **Frontend**: A Vue.js application with TypeScript and PrimeVue for displaying and managing Toolforge jobs

Key features:
- Secure API access with API key authentication
- Endpoints for retrieving job information for specific tools
- Integration with the Toolforge API (https://api.svc.tools.eqiad1.wikimedia.cloud)
- Simple and intuitive REST API design
- Interactive UI for viewing and managing jobs
- Responsive design for desktop and mobile devices

This application is designed to work within the Wikimedia ecosystem, particularly for tools that need to interact with the Toolforge infrastructure programmatically.

## Deployment



## Development

### Prerequisites

- Python 3.13 or higher
- Poetry (for dependency management)
- bun

### Backend Setup

Install backend dependencies:

```bash
poetry install
```

### Running the Backend Server

Start the FastAPI server:

```bash
X_API_KEY=abc123 poetry run web
```

The backend server will be available at http://localhost:8000.

### Frontend Setup

Install frontend dependencies:

```bash
cd frontend
bun install
```

### Running the Frontend Development Server

Start the Vue.js development server:

```bash
cd frontend
VITE_API_KEY=abc123 bun run dev
```

The frontend development server will be available at http://localhost:5173.

### Testing build

Build the frontend for production:

```bash
pack build -B tools-harbor.wmcloud.org/toolforge/heroku-builder:24_0.20.7  --buildpack heroku/python curator-web
```

This will build the frontend and output the files to the `src/curator/static` directory, where they can be served by the FastAPI backend.

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
