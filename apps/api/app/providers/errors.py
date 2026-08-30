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


class ProviderModelNotFoundError(ProviderNotConfiguredError):
    code = "provider_model_not_found"


class ProviderSelectionAmbiguousError(ProviderNotConfiguredError):
    code = "provider_selection_ambiguous"


class ProviderScenarioUnsupportedError(ProviderNotConfiguredError):
    code = "provider_scenario_unsupported"
