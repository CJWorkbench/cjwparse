from typing import Any, Dict

from cjwmodule.i18n.types import I18nMessage

__all__ = ["_trans_cjwparse"]


def _trans_cjwparse(id: str, default: str, args: Dict[str, Any] = {}) -> I18nMessage:
    """
    Build an I18nMessage for use in `cjwparse`.

    Use ``_trans_cjwparse()`` rather than building a
    :py:class:`cjwmodule.i18n.I18nMessage` directly. Workbench's i18n tooling parses
    ``_trans_cjwparse()`` calls to maintain translation files of `cjwparse`.

    Example usage::

        from cjwparse.i18n import _trans_cjwparse

        except ApiException as err:  # some
            return _trans_cjwparse(
                "greatapi.exception.message",
                "Something is wrong: {error}",
                {"error": str(err)}
            )

    :param id: Message ID unique to this module (e.g., ``"errors.allNull"``)
    :param default: English-language message, in ICU format. (e.g.,
                    ``"The column “{column}” must contain non-null values.")``
    :param args: Values to interpolate into the message. (e.g.,
                 ``{"column": "A"}```
    """
    return I18nMessage(id, args, "cjwparse")
