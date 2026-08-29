from fastapi import Request

from mock_provider.core.config import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
