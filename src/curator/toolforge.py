import functools
import os
from typing import Any, Callable, Dict, Optional, TypeVar

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

T = TypeVar("T")

TOOLFORGE_API_URL = os.getenv(
    "TOOL_TOOLFORGE_API_URL", "https://api.svc.tools.eqiad1.wikimedia.cloud:30003"
)
X_USERNAME = os.getenv("X_USERNAME")

# Create a router for toolforge endpoints
router = APIRouter(prefix="/api/toolforge", tags=["toolforge"])


class JobConfig(BaseModel):
    """
    Pydantic model for job configuration.
    """

    name: str = Field(..., description="Unique name that identifies the job.")
    cmd: str = Field(..., description="Command that this job is executing.")
    imagename: str = Field(..., description="Container image the job uses.")
    continuous: Optional[bool] = Field(
        False, description="If a job should be always running."
    )
    cpu: Optional[str] = Field(None, description="Job CPU resource limit.")
    emails: Optional[str] = Field(None, description="Job emails setting.")
    filelog: Optional[bool] = Field(
        False, description="Whether this job uses filelog or not."
    )
    filelog_stderr: Optional[str] = Field(
        None, description="Path to the stderr file log."
    )
    filelog_stdout: Optional[str] = Field(
        None, description="Path to the stdout file log."
    )
    memory: Optional[str] = Field(None, description="Job memory resource limit.")
    mount: Optional[str] = Field(
        None, description="NFS mount configuration for the job."
    )
    port: Optional[int] = Field(
        None,
        description="Port to expose for the job. Applicable only when continuous is true.",
    )
    replicas: Optional[int] = Field(
        None,
        description="Number of replicas to be used for the job. Configurable only when continuous is true.",
    )
    retry: Optional[int] = Field(
        0, description="Job retry policy. Zero means don't retry at all (the default)"
    )
    schedule: Optional[str] = Field(
        None, description="If the job is a cronjob, execution schedule."
    )
    timeout: Optional[int] = Field(
        None,
        description="Maximum amount of seconds the job will be allowed to run before it is failed",
    )


async def verify_user(request: Request):
    """ """
    user = request.session.get("user")

    if user and user.get("username") == X_USERNAME:
        return user.get("username")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


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


async def make_toolforge_request(
    method: str, url: str, json_data: Optional[Dict[str, Any]] = None
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
    cert = (f"{home_dir}/.toolskube/client.crt", f"{home_dir}/.toolskube/client.key")

    # Create client with SSL verification disabled and client certs
    async with httpx.AsyncClient(verify=False, cert=cert) as client:
        # Make the request
        if method.lower() == "get":
            response = await client.get(url)
        elif method.lower() == "post":
            response = await client.post(url, json=json_data)
        elif method.lower() == "delete":
            response = await client.delete(url)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        # Raise an exception if the request failed
        response.raise_for_status()

        # Return the JSON response if there is one, otherwise return an empty dict
        try:
            return response.json()
        except ValueError:
            return {}


@router.get("/jobs/v1/tool/{tool_name}/jobs/")
@handle_exceptions
async def get_tool_jobs(tool_name: str):
    """
    Fetch jobs for a specific tool.

    Args:
        tool_name (str): The name of the tool.

    Returns:
        Dict[str, Any]: The jobs data
    """
    url = f"{TOOLFORGE_API_URL}/jobs/v1/tool/{tool_name}/jobs/"
    return await make_toolforge_request("get", url)


@router.post("/jobs/v1/tool/{tool_name}/jobs/")
@handle_exceptions
async def post_tool_job(
    tool_name: str, job_config: JobConfig, user: str = Depends(verify_user)
):
    """
    Create a new job for a specific tool.

    Args:
        tool_name (str): The name of the tool.
        job_config (JobConfig): The job configuration.
        user (str): The username of the user.

    Returns:
        Dict[str, Any]: The created job data
    """
    url = f"{TOOLFORGE_API_URL}/jobs/v1/tool/{tool_name}/jobs/"
    return await make_toolforge_request(
        "post", url, job_config.model_dump(exclude_unset=True)
    )


@router.delete("/jobs/v1/tool/{tool_name}/jobs/{job_id}")
@handle_exceptions
async def delete_tool_job(
    tool_name: str, job_id: str, user: str = Depends(verify_user)
):
    """
    Delete a job by its ID.

    Args:
        tool_name (str): The name of the tool.
        job_id (str): The ID of the job to delete.
        user (str): The username of the user.

    Returns:
        Dict[str, Any]: The response data
    """
    url = f"{TOOLFORGE_API_URL}/jobs/v1/tool/{tool_name}/jobs/{job_id}"
    return await make_toolforge_request("delete", url)
