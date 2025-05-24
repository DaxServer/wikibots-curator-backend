# Curator Backend

A FastAPI-based backend service for the Curator application.

## Overview

The Curator Backend is a FastAPI-based service that provides a secure interface to the Wikimedia Toolforge API. It serves as the backend component for the Curator application, enabling users to manage and monitor jobs running on Wikimedia Toolforge.

Key features:
- Secure API access with API key authentication
- Endpoints for retrieving job information for specific tools
- Integration with the Toolforge API (https://api.svc.tools.eqiad1.wikimedia.cloud)
- Simple and intuitive REST API design

This service is designed to work within the Wikimedia ecosystem, particularly for tools that need to interact with the Toolforge infrastructure programmatically.

## Installation

### Prerequisites

- Python 3.13 or higher
- Poetry (for dependency management)

### Setup

Install dependencies:

```bash
poetry install
```

## Usage

### Running the Server

Start the FastAPI server:

```bash
poetry run web
```

The server will be available at http://localhost:8000.

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
