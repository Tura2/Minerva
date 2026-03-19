# Minerva Frontend

Next.js 15+ (App Router) web dashboard for Minerva trading research copilot.

## Setup

### Prerequisites
- Node.js 18+
- npm or yarn

### Installation

1. Install dependencies:
   ```bash
   npm install
   ```

2. Configure environment:
   ```bash
   cp .env.example .env.local
   # Edit .env.local with your backend API URL
   ```

### Running the App

Development mode:
```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

Production build:
```bash
npm run build
npm start
```

### Linting and Formatting

Check code style:
```bash
npm run lint
```

Format code:
```bash
npm run format
```

## Features

### Components
- **Candidate Queue**: Review screened symbols
- **Research Viewer**: Detailed analysis tickets with charts
- **Watchlist**: Track selected symbols
- **Market Charts**: Lightweight-charts integration with OHLC data

### Chart Functionality
- Interactive candlestick rendering
- Execution level overlays (entry, stop, target)
- Pan, zoom, and fullscreen controls
- Responsive design

## Architecture

```
src/
├── app/
│   ├── layout.tsx       # Root layout
│   ├── page.tsx         # Home page
│   ├── globals.css      # Global styles
│   └── [routes]/        # Page routes (TBD)
├── components/          # React components
├── lib/
│   └── apiClient.ts     # API integration
└── types/               # TypeScript types (TBD)
```

## API Integration

All API calls use the configured `NEXT_PUBLIC_API_URL`:
- Default: `http://localhost:8000`
- Vercel deployment: Set via Vercel environment variables

## Deployment

### Vercel

1. Connect GitHub repository to Vercel
2. Set environment variables in Vercel dashboard
3. Configure build command: `cd frontend && npm run build`
4. Deploy automatically on push to main

### Environment Variables

Required for Vercel:
- `NEXT_PUBLIC_API_URL`: Backend API endpoint
