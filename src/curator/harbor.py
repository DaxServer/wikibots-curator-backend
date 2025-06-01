from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
import httpx
from pydantic import BaseModel

router = APIRouter()


class ImageArtifactTag(BaseModel):
    name: str


class ImageArtifact(BaseModel):
    tags: Optional[List[ImageArtifactTag]] = None
    extra_attrs: Optional[Dict[str, Any]] = None
    digest: Optional[str] = None


class BuildPackProcess(BaseModel):
    type: str
    command: str
    args: List[str]
    direct: bool = False


class BuildPackMetadata(BaseModel):
    processes: List[BuildPackProcess]


HARBOR_API_URL = "https://tools-harbor.wmcloud.org/api/v2.0/projects/tool-curator/repositories/wikibots/artifacts"


async def get_latest_artifact() -> ImageArtifact:
    """
    Fetches the latest artifact from Harbor
    """
    params = {
        'with_tag': 'true',
        'with_label': 'true'
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(HARBOR_API_URL, params=params)
        response.raise_for_status()
        artifacts = [ImageArtifact(**artifact) for artifact in response.json()]

    # Find the latest artifact by tag
    latest_artifact = next(
        (artifact for artifact in artifacts
         if artifact.tags and any(tag.name == 'latest' for tag in artifact.tags)),
        None
    )

    if not latest_artifact:
        raise HTTPException(status_code=404, detail="No latest artifact found")

    return latest_artifact


@router.get("/api/harbor/processes", response_model=List[BuildPackProcess])
async def get_harbor_processes():
    """
    Fetches and returns the processes from the latest Harbor artifact
    """
    try:
        latest_artifact = await get_latest_artifact()

        # Extract build metadata
        build_metadata_str = (
            latest_artifact.extra_attrs
            .get('config', {})
            .get('Labels', {})
            .get('io.buildpacks.build.metadata')
        )

        if not build_metadata_str:
            raise HTTPException(
                status_code=404,
                detail="No build metadata found in the latest artifact"
            )

        build_metadata = BuildPackMetadata.parse_raw(build_metadata_str)
        return build_metadata.processes

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Failed to fetch from Harbor: {str(e)}"
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while processing Harbor data: {str(e)}"
        ) from e
