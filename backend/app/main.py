from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import scanner, research, market
from app.config import settings

app = FastAPI(
    title="Minerva Backend",
    description="Trading Research Copilot API",
    version="0.1.0",
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(scanner.router, prefix="/scanner", tags=["scanner"])
app.include_router(research.router, prefix="/research", tags=["research"])
app.include_router(market.router, prefix="/market", tags=["market"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "minerva-backend"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
