import os
from typing import Dict, Any, Optional

import requests
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import APIKeyHeader

# Constants
API_URL = "https://api.svc.tools.eqiad1.wikimedia.cloud:30003"

# Create a router for toolforge endpoints
router = APIRouter(prefix="/api/toolforge", tags=["toolforge"])

# API key authentication
X_API_KEY = APIKeyHeader(name="X-API-KEY")


async def verify_api_key(x_api_key: str = Depends(X_API_KEY)):
    """
    Verify that the API key in the X-API-KEY header matches the one in the environment variable.

    Args:
        x_api_key (str): The API key from the X-API-KEY header.

    Returns:
        str: The API key if it's valid.

    Raises:
        HTTPException: If the API key is invalid.
    """
    api_key = os.environ.get("X_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured on server"
        )
    if x_api_key != api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    return x_api_key


def get_tool_name() -> str:
    """
    Extract the tool name from the TOOL_DATA_DIR environment variable.
    Format of TOOL_DATA_DIR is /data/project/<tool-name>

    Returns:
        str: The tool name
    """
    tool_data_dir = os.environ.get("TOOL_DATA_DIR", "")
    if not tool_data_dir:
        raise ValueError("TOOL_DATA_DIR environment variable is not set")

    # Extract tool name from /data/project/<tool-name>
    parts = tool_data_dir.strip("/").split("/")
    if len(parts) < 3:
        raise ValueError(f"Invalid TOOL_DATA_DIR format: {tool_data_dir}")

    return parts[-1]


def get_jobs(tool_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetch jobs for a specific tool.

    Args:
        tool_name (str, optional): The name of the tool. If not provided, it will be extracted from TOOL_DATA_DIR.

    Returns:
        Dict[str, Any]: The jobs data
    """
    if tool_name is None:
        tool_name = get_tool_name()

    # Get the home directory
    home_dir = os.environ.get("TOOL_DATA_DIR", ".")

    # Make the request to the Toolforge API
    response = requests.get(
        f"{API_URL}/jobs/v1/tool/{tool_name}/jobs/",
        cert=(
            f"{home_dir}/.toolskube/client.crt",
            f"{home_dir}/.toolskube/client.key"
        ),
        verify=False
    )

    # Raise an exception if the request failed
    response.raise_for_status()

    # Return the JSON response
    return response.json()


@router.get("/jobs/v1/tool/{tool_name}/jobs/")
async def get_tool_jobs(tool_name: str, api_key: str = Depends(verify_api_key)):
    """
    Fetch jobs for a specific tool.

    Args:
        tool_name (str): The name of the tool.
        api_key (str): The API key from the X-API-KEY header.

    Returns:
        Dict[str, Any]: The jobs data
    """
    try:
        return get_jobs(tool_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/v1/tool/jobs/")
async def get_current_tool_jobs(api_key: str = Depends(verify_api_key)):
    """
    Fetch jobs for the current tool.

    Args:
        api_key (str): The API key from the X-API-KEY header.

    Returns:
        Dict[str, Any]: The jobs data
    """
    try:
        return get_jobs()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
