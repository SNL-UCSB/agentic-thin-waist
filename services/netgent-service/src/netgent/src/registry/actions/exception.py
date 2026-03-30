from netgent.src.registry.exception import NetGentWorkflowError


class ActionException(NetGentWorkflowError):
    pass


class ActionError(ActionException):
    pass
