from authorization_service import AuthorizationService


def get_roi_agent_input(identity_data):
    """
    Calls Person 3's authorization service and formats
    the result for the ROI agent.
    """

    auth_service = AuthorizationService()

    result = auth_service.validate_caller(identity_data)

    return f"""
authorized={result['authorized']}
reason={result['reason']}
caller_name={result['caller_name']}
member_name={result['member_name']}
expiration_date={result['expiration_date']}
"""