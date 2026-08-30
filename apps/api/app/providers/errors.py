class ProviderError(Exception):
    code = "provider_error"
    attempt_status = "failed"


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"
    attempt_status = "timed_out"


class ProviderUnavailableError(ProviderError):
    code = "provider_unavailable"


class ProviderResponseError(ProviderError):
    code = "invalid_provider_response"


class ProviderNotConfiguredError(ProviderError):
    code = "provider_not_configured"
    attempt_status = "failed"
