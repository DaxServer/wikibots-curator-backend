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

## Installation

### Prerequisites

- Python 3.13 or higher
- Poetry (for dependency management)
- Node.js (v14 or later)
- npm or yarn

### Backend Setup

Install backend dependencies:

```bash
poetry install
```

### Frontend Setup

Install frontend dependencies:

```bash
cd frontend
npm install
# or
yarn install
```

## Usage

### Running the Backend Server

Start the FastAPI server:

```bash
poetry run web
```

The backend server will be available at http://localhost:8000.

### Running the Frontend Development Server

Start the Vue.js development server:

```bash
cd frontend
npm run serve
# or
yarn serve
```

The frontend development server will be available at http://localhost:8080.

### Building the Frontend for Production

Build the frontend for production:

```bash
cd frontend
npm run build
# or
yarn build
```

This will build the frontend and output the files to the `src/curator/static` directory, where they can be served by the FastAPI backend.

## Development

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
