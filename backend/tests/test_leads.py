import pytest
from pydantic import ValidationError

from app.leads.routes import LeadRequest


def test_lead_requires_consent_and_contact():
    with pytest.raises(ValidationError):
        LeadRequest(name="Visitor", consent=False)
    with pytest.raises(ValidationError):
        LeadRequest(name="Visitor", consent=True)
    valid = LeadRequest(name="Visitor", email="visitor@example.com", consent=True)
    assert valid.consent
