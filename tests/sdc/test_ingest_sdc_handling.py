"""
Tests for SDC handling in ingest worker, including SDC equality checking
and duplicate error status determination.
"""

import pytest

from curator.asyncapi import (
    DuplicatedSdcNotUpdatedError,
    DuplicatedSdcUpdatedError,
    ErrorLink,
    Rank,
    Statement,
    StringDataValue,
    StringValueSnak,
)
from curator.workers.ingest import _are_sdc_equal


@pytest.fixture
def sample_statement_1():
    """Create a sample statement for testing"""
    return Statement(
        mainsnak=StringValueSnak(
            property="P1",
            datavalue=StringDataValue(value="value1", type="string"),
            datatype="string",
            snaktype="value",
        ),
        type="statement",
        id="Q1$123",
        rank=Rank.NORMAL,
    )


@pytest.fixture
def sample_statement_2():
    """Create a different sample statement for testing"""
    return Statement(
        mainsnak=StringValueSnak(
            property="P2",
            datavalue=StringDataValue(value="value2", type="string"),
            datatype="string",
            snaktype="value",
        ),
        type="statement",
        id="Q1$456",
        rank=Rank.NORMAL,
    )


@pytest.fixture
def sample_statement_1_duplicate():
    """Create a statement identical to sample_statement_1"""
    return Statement(
        mainsnak=StringValueSnak(
            property="P1",
            datavalue=StringDataValue(value="value1", type="string"),
            datatype="string",
            snaktype="value",
        ),
        type="statement",
        id="Q1$123",
        rank=Rank.NORMAL,
    )


class TestAreSdcEqual:
    """Test the _are_sdc_equal function"""

    def test_equal_empty_lists(self):
        """Test that two empty lists are equal"""
        assert _are_sdc_equal([], []) is True

    def test_equal_single_statement(
        self, sample_statement_1, sample_statement_1_duplicate
    ):
        """Test that two lists with the same statement are equal"""
        sdc1 = [sample_statement_1]
        sdc2 = [sample_statement_1_duplicate]
        assert _are_sdc_equal(sdc1, sdc2) is True

    def test_equal_multiple_statements(self, sample_statement_1, sample_statement_2):
        """Test that two lists with the same statements are equal"""
        sdc1 = [sample_statement_1, sample_statement_2]
        sdc2 = [sample_statement_1, sample_statement_2]
        assert _are_sdc_equal(sdc1, sdc2) is True

    def test_not_equal_different_lengths(self, sample_statement_1):
        """Test that lists with different lengths are not equal"""
        sdc1 = [sample_statement_1]
        sdc2 = [sample_statement_1, sample_statement_1]
        assert _are_sdc_equal(sdc1, sdc2) is False

    def test_not_equal_different_statements(
        self, sample_statement_1, sample_statement_2
    ):
        """Test that lists with different statements are not equal"""
        sdc1 = [sample_statement_1]
        sdc2 = [sample_statement_2]
        assert _are_sdc_equal(sdc1, sdc2) is False

    def test_equal_order_doesnt_matter(self, sample_statement_1, sample_statement_2):
        """Test that order doesn't matter for equality"""
        sdc1 = [sample_statement_1, sample_statement_2]
        sdc2 = [sample_statement_2, sample_statement_1]
        assert _are_sdc_equal(sdc1, sdc2) is True


class TestDuplicateErrorTypes:
    """Test the new duplicate error types"""

    def test_duplicated_sdc_updated_error(self):
        """Test DuplicatedSdcUpdatedError creation"""
        error = DuplicatedSdcUpdatedError(
            message="File already exists",
            links=[ErrorLink(title="File.jpg", url="https://example.com/File.jpg")],
        )
        assert error.type == "duplicated_sdc_updated"
        assert error.message == "File already exists"
        assert len(error.links) == 1
        assert error.links[0].title == "File.jpg"

    def test_duplicated_sdc_not_updated_error(self):
        """Test DuplicatedSdcNotUpdatedError creation"""
        error = DuplicatedSdcNotUpdatedError(
            message="File already exists",
            links=[ErrorLink(title="File.jpg", url="https://example.com/File.jpg")],
        )
        assert error.type == "duplicated_sdc_not_updated"
        assert error.message == "File already exists"
        assert len(error.links) == 1
        assert error.links[0].title == "File.jpg"

    def test_duplicated_sdc_updated_error_serialization(self):
        """Test that DuplicatedSdcUpdatedError serializes correctly"""
        error = DuplicatedSdcUpdatedError(
            message="File already exists",
            links=[ErrorLink(title="File.jpg", url="https://example.com/File.jpg")],
        )
        serialized = error.model_dump(mode="json", by_alias=True, exclude_none=True)
        assert serialized["type"] == "duplicated_sdc_updated"
        assert serialized["message"] == "File already exists"
        assert len(serialized["links"]) == 1

    def test_duplicated_sdc_not_updated_error_serialization(self):
        """Test that DuplicatedSdcNotUpdatedError serializes correctly"""
        error = DuplicatedSdcNotUpdatedError(
            message="File already exists",
            links=[ErrorLink(title="File.jpg", url="https://example.com/File.jpg")],
        )
        serialized = error.model_dump(mode="json", by_alias=True, exclude_none=True)
        assert serialized["type"] == "duplicated_sdc_not_updated"
        assert serialized["message"] == "File already exists"
        assert len(serialized["links"]) == 1
