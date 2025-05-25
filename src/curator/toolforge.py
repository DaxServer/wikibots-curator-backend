import os
import functools
from typing import Dict, Any, Callable, TypeVar, Optional

import requests
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

T = TypeVar('T')

TOOLFORGE_API_URL = os.getenv('TOOL_TOOLFORGE_API_URL', "https://api.svc.tools.eqiad1.wikimedia.cloud:30003")


class JobConfig(BaseModel):
    """
    Pydantic model for job configuration.
    """
    name: str = Field(..., description="Unique name that identifies the job.")
    cmd: str = Field(..., description="Command that this job is executing.")
    imagename: str = Field(..., description="Container image the job uses.")
    continuous: bool = Field(False, description="If a job should be always running.")
    cpu: str = Field(None, description="Job CPU resource limit.")
    emails: str = Field(None, description="Job emails setting.")
    filelog: bool = Field(False, description="Whether this job uses filelog or not.")
    filelog_stderr: str = Field(None, description="Path to the stderr file log.")
    filelog_stdout: str = Field(None, description="Path to the stdout file log.")
    memory: str = Field(None, description="Job memory resource limit.")
    mount: str = Field(None, description="NFS mount configuration for the job.")
    port: int = Field(None, description="Port to expose for the job. Applicable only when continuous is true.")
    replicas: int = Field(None, description="Number of replicas to be used for the job. Configurable only when continuous is true.")
    retry: int = Field(0, description="Job retry policy. Zero means don't retry at all (the default)")
    schedule: str = Field(None, description="If the job is a cronjob, execution schedule.")
    timeout: int = Field(None, description="Maximum amount of seconds the job will be allowed to run before it is failed")


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


def handle_exceptions(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to handle exceptions in API endpoints.

    Args:
        func (Callable): The function to decorate.

    Returns:
        Callable: The decorated function.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
    return wrapper


def make_toolforge_request(
    method: str,
    url: str,
    json_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Make a request to the Toolforge API.

    Args:
        method (str): The HTTP method to use.
        url (str): The URL to make the request to.
        json_data (Optional[Dict[str, Any]]): The JSON data to send with the request.

    Returns:
        Dict[str, Any]: The response data.
    """
    # Get the home directory
    home_dir = os.environ.get("TOOL_DATA_DIR", ".")

    # Set up the certificate paths
    cert = (
        f"{home_dir}/.toolskube/client.crt",
        f"{home_dir}/.toolskube/client.key"
    )

    # Make the request
    if method.lower() == 'get':
        response = requests.get(url, cert=cert, verify=False)
    elif method.lower() == 'post':
        response = requests.post(url, json=json_data, cert=cert, verify=False)
    elif method.lower() == 'delete':
        response = requests.delete(url, cert=cert, verify=False)
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")

    # Raise an exception if the request failed
    response.raise_for_status()

    # Return the JSON response if there is one, otherwise return an empty dict
    try:
        return response.json()
    except ValueError:
        return {}


def get_jobs(tool_name: str) -> Dict[str, Any]:
    """
    Fetch jobs for a specific tool.

    Args:
        tool_name (str): The name of the tool.

    Returns:
        Dict[str, Any]: The jobs data
    """
    url = f"{TOOLFORGE_API_URL}/jobs/v1/tool/{tool_name}/jobs/"
    return make_toolforge_request('get', url)


def post_job(tool_name: str, job_config: JobConfig) -> Dict[str, Any]:
    """
    Create a new job for a specific tool.

    Args:
        tool_name (str): The name of the tool.
        job_config (JobConfig): The job configuration.

    Returns:
        Dict[str, Any]: The created job data
    """
    url = f"{TOOLFORGE_API_URL}/jobs/v1/tool/{tool_name}/jobs/"
    return make_toolforge_request('post', url, job_config.model_dump())


def delete_job(tool_name: str, job_id: str) -> Dict[str, Any]:
    """
    Delete a job by its ID.

    Args:
        tool_name (str): The name of the tool.
        job_id (str): The ID of the job to delete.

    Returns:
        Dict[str, Any]: The response data
    """
    url = f"{TOOLFORGE_API_URL}/jobs/v1/tool/{tool_name}/jobs/{job_id}"
    return make_toolforge_request('delete', url)


@router.get("/jobs/v1/tool/{tool_name}/jobs/")
@handle_exceptions
async def get_tool_jobs(tool_name: str, api_key: str = Depends(verify_api_key)):
    """
    Fetch jobs for a specific tool.

    Args:
        tool_name (str): The name of the tool.
        api_key (str): The API key from the X-API-KEY header.

    Returns:
        Dict[str, Any]: The jobs data
    """
    return get_jobs(tool_name)


@router.post("/jobs/v1/tool/{tool_name}/jobs/")
@handle_exceptions
async def post_tool_job(
        tool_name: str,
        job_config: JobConfig,
        api_key: str = Depends(verify_api_key)
):
    """
    Create a new job for a specific tool.

    Args:
        tool_name (str): The name of the tool.
        job_config (JobConfig): The job configuration.
        api_key (str): The API key from the X-API-KEY header.

    Returns:
        Dict[str, Any]: The created job data
    """
    return post_job(tool_name, job_config)


@router.delete("/jobs/v1/tool/{tool_name}/jobs/{job_id}")
@handle_exceptions
async def delete_tool_job(
        tool_name: str,
        job_id: str,
        api_key: str = Depends(verify_api_key)
):
    """
    Delete a job by its ID.

    Args:
        tool_name (str): The name of the tool.
        job_id (str): The ID of the job to delete.
        api_key (str): The API key from the X-API-KEY header.

    Returns:
        Dict[str, Any]: The response data
    """
    return delete_job(tool_name, job_id)
