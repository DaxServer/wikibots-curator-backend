"""fix_missing_sdc_globe_coordinate_fields

Revision ID: 05cabbf622bd
Revises: e63e2657da9e
Create Date: 2025-12-19 16:46:37.435051

"""

import copy
import json
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from alembic import op
from curator.app.models import UploadRequest

# revision identifiers, used by Alembic.
revision: str = "05cabbf622bd"
down_revision: Union[str, Sequence[str], None] = "e63e2657da9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: fix missing precision and altitude in SDC globecoordinate data."""
    bind = op.get_bind()
    session = Session(bind=bind)

    # Gather IDs first to avoid keeping a large number of objects in memory
    # and to allow committing individually.
    upload_request_ids = [
        r[0]
        for r in session.query(UploadRequest.id).filter(UploadRequest.sdc != sa.null()).all()
    ]

    print(upload_request_ids)

    for ur_id in upload_request_ids:
        ur = session.query(UploadRequest).get(ur_id)
        if not ur or not ur.sdc:
            continue

        sdc = ur.sdc
        
        if isinstance(sdc, str):
            try:
                sdc = json.loads(sdc)
            except json.JSONDecodeError:
                print(f"Error decoding JSON for UploadRequest {ur_id}")
                continue

        if not isinstance(sdc, list):
            print(f"Error: SDC for UploadRequest {ur_id} is not a list")
            continue

        modified = False
        new_sdc = copy.deepcopy(sdc)

        for statement in new_sdc:
            if not isinstance(statement, dict):
                continue

            # Ensure 'rank' is present
            if "rank" not in statement:
                statement["rank"] = "normal"
                modified = True

            # Ensure 'type' is present
            if "type" not in statement:
                statement["type"] = "statement"
                modified = True

            mainsnak = statement.get("mainsnak")
            if not isinstance(mainsnak, dict):
                continue

            # Ensure 'snaktype' is present in mainsnak
            if "snaktype" not in mainsnak:
                mainsnak["snaktype"] = "value"
                modified = True

            if mainsnak.get("datatype") == "globe-coordinate":
                datavalue = mainsnak.get("datavalue")
                if isinstance(datavalue, dict):
                    # Some data might have 'type': 'globe-coordinate' instead of 'globecoordinate'
                    if datavalue.get("type") in ["globecoordinate", "globe-coordinate"]:
                        if datavalue.get("type") == "globe-coordinate":
                            datavalue["type"] = "globecoordinate"
                            modified = True

                        value = datavalue.get("value")
                        if isinstance(value, dict):
                            if "precision" not in value:
                                value["precision"] = 0.000001
                                modified = True
                            if "altitude" not in value:
                                value["altitude"] = None
                                modified = True
                            if "globe" not in value:
                                value["globe"] = "http://www.wikidata.org/entity/Q2"
                                modified = True

        if modified:
            print(f"Updating UploadRequest {ur_id} with modified SDC")
            ur.sdc = new_sdc
            flag_modified(ur, "sdc")
            session.add(ur)
            session.commit()


def downgrade() -> None:
    """Downgrade schema (optional, usually not needed for data fixes)."""
    pass
