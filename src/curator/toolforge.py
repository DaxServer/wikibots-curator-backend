import os
from typing import Dict, Any

import requests
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import APIKeyHeader

TOOLFORGE_API_URL = os.getenv('TOOL_TOOLFORGE_API_URL', "https://api.svc.tools.eqiad1.wikimedia.cloud:30003")

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


def get_jobs(tool_name: str) -> Dict[str, Any]:
    """
    Fetch jobs for a specific tool.

    Args:
        tool_name (str): The name of the tool.

    Returns:
        Dict[str, Any]: The jobs data
    """
    # Get the home directory
    home_dir = os.environ.get("TOOL_DATA_DIR", ".")

    # Make the request to the Toolforge API
    response = requests.get(
        f"{TOOLFORGE_API_URL}/jobs/v1/tool/{tool_name}/jobs/",
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
