"""Terminal security configuration failures; never an assurance downgrade signal."""


class SecurityConfigurationError(ValueError):
    """A production trust path is unsupported or unsafe and must not fall back."""
