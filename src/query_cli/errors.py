class QueryCliError(Exception):
    """Error esperado: se muestra al usuario sin traceback."""


class ConfigError(QueryCliError):
    pass


class ParamError(QueryCliError):
    pass


class WriteNotAllowedError(QueryCliError):
    pass
