from cjwmodule.i18n import I18nMessage


def cjwparse_i18n_message(message_id, arguments={}):
    return I18nMessage(message_id, arguments, source="cjwparse")
