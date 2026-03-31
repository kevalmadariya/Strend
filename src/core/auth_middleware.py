from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from src.core.security import verify_token

class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow open routes
        open_paths = [
            "/login",
            "/register",
            "/docs",
            "/openapi.json",
            "/add_database"
        ]
        
        # WebSockets handle their own auth
        if request.url.path.startswith("/ws"):
            return await call_next(request)

        # Allow simple match or startswith
        if request.url.path in open_paths or any(request.url.path.startswith(p) for p in open_paths if p not in ["/login", "/register", "/add_database"]):
            return await call_next(request)

        # Check for Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header"}
            )
        
        token = auth_header.split(" ")[1]
        try:
            payload = verify_token(token)
            # Store payload in request state
            request.state.user = payload
        except HTTPException as e:
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        except Exception as e:
            return JSONResponse(status_code=401, content={"detail": "Invalid token"})

        response = await call_next(request)
        return response
