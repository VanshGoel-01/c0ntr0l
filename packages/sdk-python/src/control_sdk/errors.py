from control_schemas import RuntimeActionDecision, RuntimePreflightResult


class ControlSdkError(Exception):
    """Base class for errors raised by the c0ntr0l SDK."""


class ControlTransportError(ControlSdkError):
    """The control plane could not be reached."""


class ControlProtocolError(ControlSdkError):
    """The control plane returned a response that did not match its contract."""


class ControlApiError(ControlSdkError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"c0ntr0l API returned {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class ActionBlockedError(ControlSdkError):
    def __init__(self, decision: RuntimeActionDecision) -> None:
        super().__init__(decision.reason)
        self.decision = decision
        self.execution_id = decision.execution_id
        self.action_id = decision.action_id
        self.checkpoint_id = decision.checkpoint_id


class ModelPreflightBlockedError(ControlSdkError):
    def __init__(self, result: RuntimePreflightResult) -> None:
        super().__init__(result.reason)
        self.result = result
        self.execution_id = result.execution_id
        self.checkpoint_id = result.checkpoint_id
