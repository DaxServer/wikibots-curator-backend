![GitHub License](https://img.shields.io/github/license/DaxServer/wikibots-curator-backend?link=https%3A%2F%2Fopensource.org%2Flicense%2FMIT)

# Curator Application (TypeScript)

A modern backend service for managing and monitoring CuratorBot jobs, built with TypeScript, Bun, and Hono.

## Project Structure

```
.
├── src/
│   ├── config/       # Configuration files
│   ├── controllers/   # Request handlers
│   ├── middleware/    # Custom middleware
│   ├── models/        # Data models and types
│   ├── routes/        # Route definitions
│   ├── services/      # Business logic
│   ├── utils/         # Utility functions
│   └── index.ts       # Application entry point
├── test/             # Test files
├── .env              # Environment variables
├── .eslintrc.json    # ESLint configuration
├── .prettierrc       # Prettier configuration
├── bun.lockb         # Bun lockfile
├── package.json      # Project configuration
└── tsconfig.json     # TypeScript configuration
```

## Prerequisites

- [Bun](https://bun.sh/) (v1.0.0 or later)
- Node.js (v18.0.0 or later, for development tooling)

## Getting Started

1. **Clone the repository**

   ```bash
   git clone https://github.com/DaxServer/wikibots-curator-backend.git
   cd wikibots-curator-backend
   ```

2. **Install dependencies**

   ```bash
   bun install
   ```

3. **Set up environment variables**
   Copy `.env.example` to `.env` and update the values:

   ```bash
   cp .env.example .env
   ```

4. **Start the development server**
   ```bash
   bun run dev
   ```
   The server will be available at `http://localhost:3000`

## Development

- **Lint code**

  ```bash
  bun run lint
  ```

- **Format code**

  ```bash
  bun run format
  ```

- **Run tests**
  ```bash
  bun test
  ```

## Building for Production

1. **Build the application**

   ```bash
   bun run build
   ```

2. **Start the production server**
   ```bash
   bun run start
   ```

## Environment Variables

| Variable     | Description                          | Default            |
| ------------ | ------------------------------------ | ------------------ |
| `PORT`       | Port to run the server on            | `3000`             |
| `NODE_ENV`   | Environment (development/production) | `development`      |
| `SECRET_KEY` | Secret key for session encryption    | Randomly generated |

## Contributing

1. Fork the repository
2. Create a new branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
