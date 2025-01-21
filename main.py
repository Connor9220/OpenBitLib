from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from db_utils import (
    set_db_mode,
    delete,
    fetch_column_names,
    fetch_filtered,
    fetch_image_hash,
    fetch_shapes,
    fetch_tool_data,
    fetch_tool_numbers_and_details,
    fetch_unique_column_values,
    insert,
    update,
    update_image_hash,
)
from auth_utils import verify_hmac, generate_hmac  # Assuming these are in auth_utils.py
from settings import CONFIG  # For configuration settings
from typing import Optional
from starlette.requests import Request
from starlette.responses import JSONResponse
import json
from urllib.parse import urlencode

app = FastAPI()

# Configuration settings
TIME_WINDOW_SECONDS = CONFIG.get("hmac_time_window", 300)
HMAC_ENABLED = CONFIG.get("api", {}).get("hmac_enabled", False)
USED_NONCES = (
    set()
)  # In-memory nonce store for simplicity; replace with persistent storage for production

set_db_mode("direct", None)

from starlette.datastructures import MutableHeaders

from starlette.requests import Request
from starlette.responses import JSONResponse
import json
from datetime import datetime


@app.middleware("http")
async def hmac_validation_middleware(request: Request, call_next):
    """
    Middleware to validate HMAC signatures with URL, timestamp, and nonce.
    """
    try:
        if not HMAC_ENABLED:
            print("[INFO] HMAC validation is disabled")
            return await call_next(request)

        # Clone the request body for POST/PUT/DELETE
        if request.method in ["POST", "PUT", "DELETE"]:
            try:
                body_bytes = await request.body()
                body = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
                query_params = body if isinstance(body, dict) else {}

                # Reconstruct the request with the body restored
                async def receive():
                    return {
                        "type": "http.request",
                        "body": body_bytes,
                        "more_body": False,
                    }

                request = Request(request.scope, receive, request._send)
            except json.JSONDecodeError:
                print("[ERROR] Invalid JSON in request body")
                return JSONResponse(
                    status_code=400, content={"detail": "Invalid JSON in request body"}
                )
            except Exception as e:
                print(f"[ERROR] Error processing request body: {str(e)}")
                return JSONResponse(
                    status_code=400,
                    content={"detail": f"Error processing request body: {str(e)}"},
                )
        else:
            query_params = dict(request.query_params)

        # Preserve original query parameters for debugging
        original_query_params = query_params.copy()

        # Extract and remove the signature
        signature = query_params.pop("signature", None)

        # Validate presence of the signature
        if not signature:
            print("[ERROR] Missing signature")
            return JSONResponse(
                status_code=403, content={"detail": "Missing signature"}
            )

        # Validate timestamp and nonce
        timestamp = query_params.get("timestamp")
        nonce = query_params.get("nonce")

        if not timestamp or not nonce:
            print("[ERROR] Missing timestamp or nonce")
            return JSONResponse(
                status_code=403, content={"detail": "Missing timestamp or nonce"}
            )

        try:
            request_time = datetime.fromisoformat(timestamp)
        except ValueError:
            print("[ERROR] Invalid timestamp format")
            return JSONResponse(
                status_code=403, content={"detail": "Invalid timestamp format"}
            )

        current_time = datetime.utcnow()
        time_difference = abs((current_time - request_time).total_seconds())
        if time_difference > TIME_WINDOW_SECONDS:
            print(f"[ERROR] Timestamp outside valid time window: {time_difference}s")
            return JSONResponse(
                status_code=403,
                content={"detail": "Timestamp outside valid time window"},
            )

        # Check nonce usage
        if nonce in USED_NONCES:
            print(f"[ERROR] Nonce has already been used: {nonce}")
            return JSONResponse(
                status_code=403, content={"detail": "Nonce has already been used"}
            )
        USED_NONCES.add(nonce)

        # Reconstruct full URL for verification
        reconstructed_query = urlencode(query_params)
        separator = "&" if "?" in request.url.path else "?"
        full_url = f"{request.url.path}{separator}{reconstructed_query}"

        # Verify the HMAC signature
        if not verify_hmac(full_url, signature):
            print(f"[ERROR] Invalid signature for URL: {full_url}")
            return JSONResponse(
                status_code=403, content={"detail": "Invalid signature"}
            )

        # Proceed to the next middleware or endpoint
        return await call_next(request)

    except Exception as e:
        print(f"[ERROR] Server error during HMAC validation: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Server error during HMAC validation: {str(e)}"},
        )


@app.delete("/delete/{table}/{id}")
async def api_delete(table: str, id: int):
    try:
        result = delete(id)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/column_names/{table}")
async def api_fetch_column_names(table: str):
    try:
        result = fetch_column_names(table)
        return {"column_names": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/image_hash/{tool_id}")
async def api_fetch_image_hash(tool_id: int):
    try:
        result = fetch_image_hash(tool_id)
        return {"image_hash": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/shapes")
async def api_fetch_shapes(shape_name: Optional[str] = None):
    """
    API endpoint to fetch shapes or specific shape details.

    Args:
        shape_name (Optional[str]): The name of the shape to fetch. If None, fetches all shapes.

    Returns:
        dict: A dictionary containing the list of shapes or specific shape details.
    """
    try:
        result = fetch_shapes(shape_name=shape_name)
        return {"shapes": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tool_data")
async def get_tool_data(tool_number: Optional[int] = None):
    """
    Fetch tool data. If no tool_number is provided, fetch all tools.

    Args:
        tool_number (Optional[int]): The tool number to filter by.

    Returns:
        dict: A dictionary containing tool data rows and column names.
    """
    try:
        if tool_number is None:
            # Fetch all tools
            tools, columns = fetch_tool_data()
        else:
            # Fetch a specific tool
            tools, columns = fetch_tool_data(tool_number=tool_number)

        return {"tools": tools, "columns": columns}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/filtered")
async def api_fetch_filtered(keyword: str):
    try:
        tools, columns = fetch_filtered(keyword)
        return {"tools": tools, "columns": columns}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tool_numbers_and_details")
async def api_fetch_tool_numbers_and_details():
    try:
        result = fetch_tool_numbers_and_details()
        return {"tool_numbers_and_details": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/unique_column_values/{table}/{column}")
async def api_fetch_unique_column_values(table: str, column: str):
    try:
        result = fetch_unique_column_values(column)
        return {"unique_values": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/insert/{table}")
async def api_insert(table: str, data: dict):
    try:
        result = insert(data)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/update/{table}/{id}")
async def api_update(table: str, id: int, data: dict):
    try:
        result = update(id, data)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/update_image_hash/{tool_id}")
async def api_update_image_hash(tool_id: int, hash_value: str):
    try:
        result = update_image_hash(tool_id, hash_value)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
